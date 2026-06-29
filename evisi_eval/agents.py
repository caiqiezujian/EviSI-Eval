"""
EviSI-Eval v0.4 — Agent-based evaluation architecture.

Three agents replace the 16-stage hardcoded pipeline:
  SourceWorker  — analyzes source text (never sees translations)
  TargetWorker  — analyzes SI translation (never sees source analysis)
  MainAgent     — judges fidelity, scores, summarizes (only sees structured data)

AgentLoop coordinates them with optional reanalysis rounds.

Information isolation is enforced at the code level — each agent's payload
physically excludes data it must not see.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from .llm_provider import LLMClient, LLMResponse
from .prompt_loader import load_prompt, prompt_manifest
from .validation import (
    DIMENSION_WEIGHTS,
    validate_anchor_extraction,
    validate_dimension_scores,
    validate_eval_units,
    validate_event_extraction,
    validate_final_summary,
    validate_global_review,
    validate_issue_evaluation,
    validate_judgements,
    validate_relation_extraction,
    validate_source_units,
    weighted_score,
)

PROTOCOL_VERSION = "evisi_eval_v0.4"
MAX_REPAIR_ATTEMPTS = 2
MAX_REANALYSIS_ROUNDS = 3
ArtifactSink = Callable[[str, dict[str, Any]], None]


# ──────────────────────────────────────────────
# Stage runner (shared repair loop)
# ──────────────────────────────────────────────

@dataclass
class StageResult:
    artifact: dict[str, Any]
    traces: list[dict[str, Any]]
    initial_issues: list[str]
    fallback_used: bool


class Runner:
    """Generic LLM → validate → repair → fallback loop. Shared by all agents."""

    def __init__(self, client: LLMClient):
        self.client = client

    def run(
        self,
        stage_name: str,
        payload: dict[str, Any],
        validator: Callable[[dict[str, Any]], list[str]],
        fallback: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> StageResult:
        response = self.client.generate_json(
            load_prompt(stage_name), payload, task=stage_name
        )
        traces = [_trace(stage_name, response)]
        artifact = _canonicalize(stage_name, response.data, payload)
        initial_issues = validator(artifact)
        issues = list(initial_issues)

        for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
            if not issues:
                break
            artifact = _repair_once(
                self.client, stage_name, payload, artifact, issues, attempt, traces
            )
            issues = validator(artifact)

        fallback_used = False
        if issues and fallback is not None:
            artifact = _canonicalize(stage_name, fallback(artifact), payload)
            issues = validator(artifact)
            fallback_used = True
            traces.append(_fallback_trace(stage_name))

        if issues:
            raise ValueError(
                f"{stage_name} failed validation: {'; '.join(issues)}"
            )
        return StageResult(artifact, traces, initial_issues, fallback_used)


# ──────────────────────────────────────────────
# SourceWorker
# ──────────────────────────────────────────────

class SourceWorker:
    """Analyzes source text. Never receives any translation data."""

    PROMPT = "source_worker"

    def __init__(self, client: LLMClient):
        self.runner = Runner(client)
        self.client = client

    def analyze(
        self, sample: dict[str, Any], focus: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        sample_id = _required(sample, "sample_id")
        source_text = _required(sample, "source_text")

        payload = {
            "sample_id": sample_id,
            "source_text": source_text,
            "src_lang": sample.get("src_lang", "unspecified"),
            "tgt_lang": sample.get("tgt_lang", "unspecified"),
            "domain": sample.get("domain", "unspecified"),
            "focus": focus,
        }

        result = self.runner.run(
            self.PROMPT,
            payload,
            lambda a: _validate_source_worker(a, source_text),
            fallback=lambda a: _source_fallback(a, source_text),
        )
        return result.artifact, result.traces


def _validate_source_worker(artifact: dict, source_text: str) -> list[str]:
    issues: list[str] = []
    issues.extend(validate_source_units(artifact, source_text))
    source_units = _records(artifact.get("source_units"))
    if source_units:
        issues.extend(validate_anchor_extraction(artifact, source_units, True))
        issues.extend(validate_event_extraction(artifact, source_units, True))
        source_events = _records(artifact.get("source_events"))
        issues.extend(
            validate_relation_extraction(artifact, source_units, source_events, True)
        )
    return issues


def _source_fallback(artifact: dict, source_text: str) -> dict:
    """Deterministic fallback: keep one unit with full text, salvage valid items."""
    artifact["source_units"] = [
        {"source_unit_id": "S1", "source_unit": source_text}
    ]
    source_units = artifact["source_units"]
    artifact["source_anchors"] = _salvage_items(
        artifact, "source_anchors", source_units, "source_unit_id",
        "source_unit", "source_anchor_id", "SA",
        ("anchor_text", "normalized_meaning"),
    )
    artifact["source_events"] = _salvage_items(
        artifact, "source_events", source_units, "source_unit_id",
        "source_unit", "source_event_id", "SE",
        ("event_text", "canonical_meaning"),
    )
    source_events = _records(artifact.get("source_events"))
    artifact["source_relations"] = _salvage_relations(
        artifact, source_units, source_events, True,
    )
    return artifact


# ──────────────────────────────────────────────
# TargetWorker
# ──────────────────────────────────────────────

class TargetWorker:
    """Analyzes SI translation. Only receives source_units (id + text) for
    alignment — never sees source anchors, events, or relations."""

    PROMPT = "target_worker"

    def __init__(self, client: LLMClient):
        self.runner = Runner(client)
        self.client = client

    def analyze(
        self,
        source_units: list[dict[str, Any]],
        output: dict[str, Any],
        focus: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        sample_id = _required(output, "sample_id")
        translation = _required(output, "si_translation")

        # Isolation: only id + text, never source analysis results
        unit_view = [
            {"source_unit_id": u["source_unit_id"], "source_unit": u["source_unit"]}
            for u in source_units
        ]

        payload = {
            "sample_id": sample_id,
            "system_name": "anonymous_system",
            "si_translation": translation,
            "source_units": unit_view,
            "focus": focus,
        }

        result = self.runner.run(
            self.PROMPT,
            payload,
            lambda a: _validate_target_worker(a, source_units, translation),
            fallback=lambda a: _target_fallback(a, source_units, translation),
        )
        return result.artifact, result.traces


def _validate_target_worker(
    artifact: dict, source_units: list[dict], translation: str
) -> list[str]:
    issues: list[str] = []
    issues.extend(validate_eval_units(artifact, source_units, translation))
    target_view = _target_unit_view(artifact)
    if target_view:
        issues.extend(validate_anchor_extraction(artifact, target_view, False))
        issues.extend(validate_event_extraction(artifact, target_view, False))
        target_events = _records(artifact.get("target_events"))
        issues.extend(
            validate_relation_extraction(artifact, target_view, target_events, False)
        )
    issues.extend(
        validate_issue_evaluation(
            artifact, translation, "fluency_issues", "fluency_assessment", "F"
        )
    )
    issues.extend(
        validate_issue_evaluation(
            artifact, translation,
            "si_expression_issues", "si_expression_assessment", "X",
        )
    )
    return issues


def _target_fallback(
    artifact: dict, source_units: list[dict], translation: str
) -> dict:
    """Deterministic fallback: collapse to one eval_unit, salvage valid items."""
    source_ids = [str(u.get("source_unit_id")) for u in source_units]
    artifact["eval_units"] = [
        {
            "eval_unit_id": "E1",
            "source_unit_ids": source_ids,
            "target_unit": translation,
            "alignment_status": "uncertain",
            "reason": "结构修复失败后保留完整双侧文本，等待人工复核",
        }
    ]
    eval_units = artifact["eval_units"]
    target_view = _target_unit_view(artifact)
    artifact["target_anchors"] = _salvage_items(
        artifact, "target_anchors", target_view, "eval_unit_id",
        "target_unit", "target_anchor_id", "TA",
        ("anchor_text", "normalized_meaning"),
    )
    artifact["target_events"] = _salvage_items(
        artifact, "target_events", target_view, "eval_unit_id",
        "target_unit", "target_event_id", "TE",
        ("event_text", "canonical_meaning"),
    )
    target_events = _records(artifact.get("target_events"))
    artifact["target_relations"] = _salvage_relations(
        artifact, target_view, target_events, False,
    )
    # Fluency / SI expression issues are non-critical for structure;
    # keep whatever the LLM returned or default to empty.
    if not isinstance(artifact.get("fluency_issues"), list):
        artifact["fluency_issues"] = []
    if not isinstance(artifact.get("si_expression_issues"), list):
        artifact["si_expression_issues"] = []
    if not artifact.get("fluency_assessment"):
        artifact["fluency_assessment"] = "结构修复，建议人工复核。"
    if not artifact.get("si_expression_assessment"):
        artifact["si_expression_assessment"] = "结构修复，建议人工复核。"
    return artifact


def _target_unit_view(artifact: dict) -> list[dict]:
    return [
        {"eval_unit_id": r["eval_unit_id"], "target_unit": r.get("target_unit", "")}
        for r in _records(artifact.get("eval_units"))
    ]


# ──────────────────────────────────────────────
# MainAgent
# ──────────────────────────────────────────────

class MainAgent:
    """Evaluates fidelity and produces scores. Only receives structured data
    from SourceWorker and TargetWorker — never raw source_text or si_translation."""

    PROMPT = "main_agent"

    def __init__(self, client: LLMClient):
        self.runner = Runner(client)
        self.client = client

    def evaluate(
        self,
        source_card: dict[str, Any],
        target_card: dict[str, Any],
        previous_round: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        payload = {
            "sample_id": source_card["sample_id"],
            "source_card": {
                "source_units": source_card["source_units"],
                "source_anchors": source_card["source_anchors"],
                "source_events": source_card["source_events"],
                "source_relations": source_card["source_relations"],
            },
            "target_eval_card": {
                "eval_units": target_card["eval_units"],
                "target_anchors": target_card["target_anchors"],
                "target_events": target_card["target_events"],
                "target_relations": target_card["target_relations"],
                "fluency_issues": target_card["fluency_issues"],
                "fluency_assessment": target_card["fluency_assessment"],
                "si_expression_issues": target_card["si_expression_issues"],
                "si_expression_assessment": target_card["si_expression_assessment"],
            },
            "previous_round": previous_round,
        }

        source_anchors = _records(source_card.get("source_anchors"))
        source_events = _records(source_card.get("source_events"))
        source_relations = _records(source_card.get("source_relations"))
        target_anchors = _records(target_card.get("target_anchors"))
        target_events = _records(target_card.get("target_events"))
        target_relations = _records(target_card.get("target_relations"))
        eval_units = _records(target_card.get("eval_units"))

        def validate(artifact: dict) -> list[str]:
            return _validate_main_agent(
                artifact,
                source_anchors, target_anchors,
                source_events, target_events,
                source_relations, target_relations,
                eval_units,
            )

        def fallback(artifact: dict) -> dict:
            return _main_fallback(
                artifact,
                source_anchors, target_anchors,
                source_events, target_events,
                source_relations, target_relations,
                eval_units,
            )

        result = self.runner.run(self.PROMPT, payload, validate, fallback=fallback)
        return result.artifact, result.traces


def _validate_main_agent(
    artifact: dict,
    source_anchors: list[dict], target_anchors: list[dict],
    source_events: list[dict], target_events: list[dict],
    source_relations: list[dict], target_relations: list[dict],
    eval_units: list[dict],
) -> list[str]:
    issues: list[str] = []
    if source_anchors:
        issues.extend(
            validate_judgements(
                artifact, source_anchors, target_anchors, eval_units, "anchor"
            )
        )
    if source_events:
        issues.extend(
            validate_judgements(
                artifact, source_events, target_events, eval_units, "event"
            )
        )
    if source_relations:
        issues.extend(
            validate_judgements(
                artifact, source_relations, target_relations, eval_units, "relation"
            )
        )
    issues.extend(validate_global_review(artifact))
    issues.extend(validate_dimension_scores(artifact))

    # Validate final_summary against program-computed score
    scores = artifact.get("dimension_scores", {})
    computed = weighted_score(scores) if scores else 0
    issues.extend(validate_final_summary(artifact, computed))
    return issues


def _main_fallback(
    artifact: dict,
    source_anchors: list[dict], target_anchors: list[dict],
    source_events: list[dict], target_events: list[dict],
    source_relations: list[dict], target_relations: list[dict],
    eval_units: list[dict],
) -> dict:
    """Deterministic salvage for MainAgent output."""
    artifact["anchor_judgements"] = _salvage_judgements(
        artifact, source_anchors, target_anchors, eval_units, "anchor"
    )["anchor_judgements"]
    artifact["event_judgements"] = _salvage_judgements(
        artifact, source_events, target_events, eval_units, "event"
    )["event_judgements"]
    artifact["relation_judgements"] = _salvage_judgements(
        artifact, source_relations, target_relations, eval_units, "relation"
    )["relation_judgements"]
    if not isinstance(artifact.get("global_fidelity_review"), dict):
        artifact["global_fidelity_review"] = {
            "delayed_expression_notes": [],
            "consistency_notes": [],
            "possible_duplicate_errors": [],
            "missed_global_issues": [],
            "misleading_addition_notes": [],
            "overall_fidelity_comment": "结构修复，建议人工复核。",
        }
    # Ensure dimension_scores exist
    if not isinstance(artifact.get("dimension_scores"), dict) or set(
        artifact.get("dimension_scores", {})
    ) != {"anchor_fidelity", "event_fidelity", "relation_fidelity", "fluency", "si_expression"}:
        artifact["dimension_scores"] = {
            "anchor_fidelity": 50,
            "event_fidelity": 50,
            "relation_fidelity": 50,
            "fluency": 50,
            "si_expression": 50,
        }
    if not isinstance(artifact.get("dimension_score_explanations"), dict):
        artifact["dimension_score_explanations"] = {
            k: "结构修复，建议人工复核。" for k in artifact["dimension_scores"]
        }
    # Recompute final_score
    artifact["final_score"] = weighted_score(artifact["dimension_scores"])
    artifact["dimension_weights"] = dict(DIMENSION_WEIGHTS)
    if not isinstance(artifact.get("score_summary"), dict):
        artifact["score_summary"] = {
            "overall_judgement": "结构修复，建议人工复核。",
            "main_strengths": [],
            "main_errors": [],
            "uncertain_points": [],
        }
    # Ensure no reanalysis request survives fallback
    if "reanalysis_request" in artifact:
        del artifact["reanalysis_request"]
    return artifact


# ──────────────────────────────────────────────
# AgentLoop
# ──────────────────────────────────────────────

class AgentLoop:
    """Coordinates SourceWorker → TargetWorker → MainAgent with optional
    reanalysis rounds.

    The MainAgent can request reanalysis from either worker if it detects
    missing or inconsistent data. The loop respects a maximum number of
    reanalysis rounds to guarantee termination.
    """

    def __init__(
        self,
        client: LLMClient,
        max_reanalysis: int = MAX_REANALYSIS_ROUNDS,
    ):
        self.client = client
        self.source_worker = SourceWorker(client)
        self.target_worker = TargetWorker(client)
        self.main_agent = MainAgent(client)
        self.max_reanalysis = max_reanalysis

        # Exposed for tests and reporting
        self.provider_name = client.provider_name
        self.model_name = client.model_name

    def run(
        self,
        sample: dict[str, Any],
        output: dict[str, Any],
        source_sink: ArtifactSink | None = None,
        target_sink: ArtifactSink | None = None,
        score_sink: ArtifactSink | None = None,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        """Execute the full agent evaluation loop for one sample × system pair.

        Returns (final_result, artifacts_dict).
        """
        sample_id = _required(sample, "sample_id")
        system_name = _required(output, "system_name")
        if sample_id != str(output.get("sample_id", "")):
            raise ValueError("system output sample_id does not match sample")

        artifacts: dict[str, dict[str, Any]] = {}
        all_traces: list[dict[str, Any]] = []
        validation_log: dict[str, Any] = {}

        # ── Phase 1: SourceWorker ──
        source_artifact, source_traces = self.source_worker.analyze(sample)
        source_card = _build_source_card(sample, source_artifact, source_traces, self.client)
        artifacts["source_cards"] = source_card
        all_traces.extend(source_traces)
        _log_validation("source_worker", validation_log, {})
        if source_sink:
            source_sink("source_cards", source_card)

        # ── Phase 2: TargetWorker ──
        target_artifact, target_traces = self.target_worker.analyze(
            source_card["source_units"], output
        )
        target_card = _build_target_card(
            output, target_artifact, target_traces, self.client
        )
        artifacts["target_eval_cards"] = target_card
        all_traces.extend(target_traces)
        _log_validation("target_worker", validation_log, {})
        if target_sink:
            target_sink("target_eval_cards", target_card)

        # ── Phase 3: MainAgent with reanalysis loop ──
        previous_round = None
        final_artifact = None

        for round_idx in range(self.max_reanalysis + 1):
            main_artifact, main_traces = self.main_agent.evaluate(
                source_card, target_card, previous_round,
            )
            all_traces.extend(main_traces)

            reanalysis = main_artifact.get("reanalysis_request")
            if reanalysis is None or not isinstance(reanalysis, dict):
                # No reanalysis requested — we're done
                final_artifact = main_artifact
                break

            # Handle reanalysis
            target = str(reanalysis.get("target") or "")
            focus = {
                "reason": reanalysis.get("reason", ""),
                "focus": reanalysis.get("focus", ""),
                "instructions": reanalysis.get("instructions", ""),
            }

            if target == "source_worker":
                source_artifact, source_traces = self.source_worker.analyze(
                    sample, focus=focus,
                )
                source_card = _build_source_card(
                    sample, source_artifact, source_traces, self.client
                )
                artifacts["source_cards"] = source_card
                all_traces.extend(source_traces)
                if source_sink:
                    source_sink("source_cards", source_card)
            elif target == "target_worker":
                target_artifact, target_traces = self.target_worker.analyze(
                    source_card["source_units"], output, focus=focus,
                )
                target_card = _build_target_card(
                    output, target_artifact, target_traces, self.client
                )
                artifacts["target_eval_cards"] = target_card
                all_traces.extend(target_traces)
                if target_sink:
                    target_sink("target_eval_cards", target_card)

            previous_round = {
                "round": round_idx + 1,
                "reanalysis_request": reanalysis,
            }

        # If all rounds consumed and still no final result, use last output
        if final_artifact is None:
            final_artifact = main_artifact

        # ── Phase 4: Build final result ──
        final_result = _build_final_result(
            source_card, target_card, final_artifact, all_traces, self.client
        )
        artifacts["score_06_final_results"] = final_result
        if score_sink:
            score_sink("score_06_final_results", final_result)

        return final_result, artifacts


# ──────────────────────────────────────────────
# Card builders
# ──────────────────────────────────────────────

def _build_source_card(
    sample: dict, artifact: dict, traces: list[dict], client: LLMClient,
) -> dict[str, Any]:
    card = {
        "sample_id": artifact.get("sample_id", sample.get("sample_id")),
        "source_text": sample.get("source_text", ""),
        "reference_translation": sample.get("reference_translation"),
        "src_lang": sample.get("src_lang", "unspecified"),
        "tgt_lang": sample.get("tgt_lang", "unspecified"),
        "domain": sample.get("domain", "unspecified"),
        "source_units": _records(artifact.get("source_units")),
        "source_anchors": _records(artifact.get("source_anchors")),
        "source_events": _records(artifact.get("source_events")),
        "source_relations": _records(artifact.get("source_relations")),
        "metadata": {
            "protocol_version": PROTOCOL_VERSION,
            "provider": client.provider_name,
            "model": client.model_name,
            "system_outputs_visible": False,
            "reference_translation_used": False,
            "agent_trace": traces,
            "prompt_hashes": prompt_manifest(),
        },
    }
    card["metadata"]["source_card_hash"] = _artifact_hash(card)
    return card


def _build_target_card(
    output: dict, artifact: dict, traces: list[dict], client: LLMClient,
) -> dict[str, Any]:
    card = {
        "sample_id": artifact.get("sample_id", output.get("sample_id")),
        "system_name": output.get("system_name", ""),
        "si_translation": output.get("si_translation", ""),
        "eval_units": _records(artifact.get("eval_units")),
        "target_anchors": _records(artifact.get("target_anchors")),
        "target_events": _records(artifact.get("target_events")),
        "target_relations": _records(artifact.get("target_relations")),
        "fluency_issues": _records(artifact.get("fluency_issues")),
        "fluency_assessment": artifact.get("fluency_assessment", ""),
        "si_expression_issues": _records(artifact.get("si_expression_issues")),
        "si_expression_assessment": artifact.get("si_expression_assessment", ""),
        "metadata": {
            "protocol_version": PROTOCOL_VERSION,
            "provider": client.provider_name,
            "model": client.model_name,
            "system_name_visible_to_agents": False,
            "reference_translation_used": False,
            "agent_trace": traces,
        },
    }
    return card


def _build_final_result(
    source_card: dict,
    target_card: dict,
    artifact: dict,
    all_traces: list[dict],
    client: LLMClient,
) -> dict[str, Any]:
    scores = artifact.get("dimension_scores", {})
    final_score = weighted_score(scores) if scores else 0
    return {
        "sample_id": source_card["sample_id"],
        "system_name": target_card["system_name"],
        "source_text": source_card["source_text"],
        "reference_translation": source_card.get("reference_translation"),
        "si_translation": target_card["si_translation"],
        "source_card_hash": source_card["metadata"]["source_card_hash"],
        "source_units": source_card["source_units"],
        "eval_units": target_card["eval_units"],
        "source_anchors": source_card["source_anchors"],
        "target_anchors": target_card["target_anchors"],
        "source_events": source_card["source_events"],
        "target_events": target_card["target_events"],
        "source_relations": source_card["source_relations"],
        "target_relations": target_card["target_relations"],
        "anchor_judgements": _records(artifact.get("anchor_judgements")),
        "anchor_fidelity_assessment": artifact.get("anchor_fidelity_assessment", ""),
        "event_judgements": _records(artifact.get("event_judgements")),
        "event_fidelity_assessment": artifact.get("event_fidelity_assessment", ""),
        "relation_judgements": _records(artifact.get("relation_judgements")),
        "relation_fidelity_assessment": artifact.get("relation_fidelity_assessment", ""),
        "fluency_issues": target_card["fluency_issues"],
        "fluency_assessment": target_card["fluency_assessment"],
        "si_expression_issues": target_card["si_expression_issues"],
        "si_expression_assessment": target_card["si_expression_assessment"],
        "global_fidelity_review": artifact.get("global_fidelity_review", {}),
        "dimension_scores": scores,
        "dimension_score_explanations": artifact.get("dimension_score_explanations", {}),
        "dimension_weights": dict(DIMENSION_WEIGHTS),
        "final_score": final_score,
        "score_summary": artifact.get("score_summary", {}),
        "metadata": {
            "protocol_version": PROTOCOL_VERSION,
            "provider": client.provider_name,
            "model": client.model_name,
            "system_name_visible_to_agents": False,
            "reference_translation_used": False,
            "agent_trace": all_traces,
            "prompt_hashes": prompt_manifest(),
        },
    }


# ──────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────

def _repair_once(
    client: LLMClient,
    stage_name: str,
    payload: dict,
    artifact: dict,
    issues: list[str],
    attempt: int,
    traces: list[dict],
) -> dict:
    repair_payload = {
        "stage_name": stage_name,
        "stage_input": payload,
        "validation_issues": issues,
        "repair_attempt": attempt,
        "json_to_repair": artifact,
    }
    repair = client.generate_json(
        load_prompt("schema_repair"), repair_payload, task=f"repair_{stage_name}"
    )
    traces.append(_trace(f"repair_{stage_name}", repair))
    return _canonicalize(stage_name, repair.data, payload)


def _canonicalize(
    stage_name: str, raw: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    """Ensure required metadata keys and list-typed fields are present."""
    artifact = dict(raw) if isinstance(raw, dict) else {}
    for meta_key in ("sample_id", "system_name"):
        if meta_key in payload:
            artifact.setdefault(meta_key, payload[meta_key])

    # Known list keys for each agent prompt
    list_keys: dict[str, str] = {
        "source_worker": None,  # handled separately below
        "target_worker": None,
        "main_agent": None,
    }
    source_lists = ["source_units", "source_anchors", "source_events", "source_relations"]
    target_lists = [
        "eval_units", "target_anchors", "target_events", "target_relations",
        "fluency_issues", "si_expression_issues",
    ]
    main_lists = [
        "anchor_judgements", "event_judgements", "relation_judgements",
    ]

    if stage_name == "source_worker":
        for key in source_lists:
            if not isinstance(artifact.get(key), list):
                artifact[key] = []
    elif stage_name == "target_worker":
        for key in target_lists:
            if not isinstance(artifact.get(key), list):
                artifact[key] = []
    elif stage_name == "main_agent":
        for key in main_lists:
            if not isinstance(artifact.get(key), list):
                artifact[key] = []
    elif stage_name in {
        "source_relation_extraction", "target_relation_extraction",
    }:
        # Legacy: migrate evidence_span → evidence_spans
        key = (
            "source_relations"
            if stage_name.startswith("source") else "target_relations"
        )
        for rel in artifact.get(key, []):
            if isinstance(rel, dict) and "evidence_spans" not in rel:
                singular = rel.pop("evidence_span", None)
                rel["evidence_spans"] = (
                    [singular] if isinstance(singular, str) and singular else []
                )

    return artifact


def _log_validation(
    stage: str, log: dict[str, Any], stage_log: dict[str, Any]
) -> None:
    log[stage] = stage_log


def _trace(task: str, response: LLMResponse) -> dict[str, Any]:
    return {
        "task": task,
        "provider": response.provider,
        "model": response.model,
        "request_id": response.request_id,
        "usage": response.usage,
    }


def _fallback_trace(stage_name: str) -> dict[str, Any]:
    return {
        "task": f"fallback_{stage_name}",
        "provider": "deterministic",
        "model": "local",
        "request_id": None,
        "usage": {},
    }


def _required(row: dict[str, Any], key: str) -> str:
    value = str(row.get(key) or "")
    if not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _artifact_hash(artifact: dict[str, Any]) -> str:
    payload = {k: v for k, v in artifact.items() if k != "metadata"}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


# ──────────────────────────────────────────────
# Salvage helpers (deterministic, no semantic judgement)
# ──────────────────────────────────────────────

def _salvage_items(
    artifact: dict[str, Any],
    list_key: str,
    units: list[dict[str, Any]],
    unit_id_key: str,
    unit_text_key: str,
    item_id_key: str,
    prefix: str,
    required_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Keep only items with valid unit ref and verbatim evidence."""
    unit_by_id = {
        str(row.get(unit_id_key)): str(row.get(unit_text_key) or "")
        for row in units
    }
    kept: list[dict[str, Any]] = []
    for row in artifact.get(list_key, []):
        if not isinstance(row, dict):
            continue
        unit_id = str(row.get(unit_id_key) or "")
        evidence = str(row.get("evidence_span") or "")
        if unit_id not in unit_by_id or not evidence:
            continue
        if evidence not in unit_by_id[unit_id]:
            continue
        if any(not str(row.get(k) or "").strip() for k in required_fields):
            continue
        row = dict(row)
        row[item_id_key] = f"{prefix}{len(kept) + 1}"
        kept.append(row)
    return kept


def _salvage_relations(
    artifact: dict[str, Any],
    units: list[dict[str, Any]],
    events: list[dict[str, Any]],
    source_side: bool,
) -> list[dict[str, Any]]:
    list_key = "source_relations" if source_side else "target_relations"
    relation_id_key = "source_relation_id" if source_side else "target_relation_id"
    prefix = "SR" if source_side else "TR"
    unit_ids_key = "source_unit_ids" if source_side else "eval_unit_ids"
    unit_id_key = "source_unit_id" if source_side else "eval_unit_id"
    unit_text_key = "source_unit" if source_side else "target_unit"
    related_key = (
        "related_source_event_ids" if source_side else "related_target_event_ids"
    )
    event_id_key = "source_event_id" if source_side else "target_event_id"

    unit_by_id = {
        str(row.get(unit_id_key)): str(row.get(unit_text_key) or "")
        for row in units
    }
    unit_order = {k: i for i, k in enumerate(unit_by_id)}
    event_ids = {str(row.get(event_id_key)) for row in events}
    kept: list[dict[str, Any]] = []

    for row in artifact.get(list_key, []):
        if not isinstance(row, dict):
            continue
        selected_ids = [
            item for item in row.get(unit_ids_key, []) if isinstance(item, str)
        ]
        indexes = [unit_order[i] for i in selected_ids if i in unit_order]
        evidence = [
            item
            for item in row.get("evidence_spans", [])
            if isinstance(item, str) and item
        ]
        selected_texts = [
            unit_by_id[i] for i in selected_ids if i in unit_by_id
        ]
        if (
            not selected_ids
            or len(indexes) != len(selected_ids)
            or indexes != list(range(min(indexes), max(indexes) + 1))
            or not evidence
            or any(
                not any(span in text for text in selected_texts)
                for span in evidence
            )
            or any(
                item not in event_ids for item in row.get(related_key, [])
            )
            or not str(row.get("relation_text") or "").strip()
            or not str(row.get("relation_meaning") or "").strip()
        ):
            continue
        row = dict(row)
        row[relation_id_key] = f"{prefix}{len(kept) + 1}"
        kept.append(row)
    return kept


def _salvage_judgements(
    artifact: dict[str, Any],
    source_items: list[dict[str, Any]],
    target_items: list[dict[str, Any]],
    eval_units: list[dict[str, Any]],
    kind: str,
) -> dict[str, Any]:
    config = {
        "anchor": (
            "anchor_judgements", "anchor_judgement_id", "AJ",
            "source_anchor_id", "source_anchor", "anchor_text",
            "target_anchor_ids", "target_anchor_id",
            {"correct", "partially_correct", "incorrect", "missing", "uncertain"},
            "anchor_fidelity_assessment",
        ),
        "event": (
            "event_judgements", "event_judgement_id", "EJ",
            "source_event_id", "source_event", "event_text",
            "target_event_ids", "target_event_id",
            {"correct", "partially_correct", "incorrect", "missing", "uncertain"},
            "event_fidelity_assessment",
        ),
        "relation": (
            "relation_judgements", "relation_judgement_id", "RJ",
            "source_relation_id", "source_relation", "relation_text",
            "target_relation_ids", "target_relation_id",
            {"correct", "weakened", "incorrect", "missing", "uncertain"},
            "relation_fidelity_assessment",
        ),
    }[kind]
    (
        list_key, judgement_id_key, prefix, source_id_key,
        source_text_key, source_value_key, target_ids_key, target_id_key,
        allowed_verdicts, assessment_key,
    ) = config

    rows_by_source = {
        str(row.get(source_id_key)): row
        for row in artifact.get(list_key, [])
        if isinstance(row, dict) and row.get(source_id_key)
    }
    target_by_id = {str(row.get(target_id_key)): row for row in target_items}
    target_text = "".join(
        str(row.get("target_unit") or "") for row in eval_units
    )
    eval_ids = {str(row.get("eval_unit_id")) for row in eval_units}
    output_rows = []

    for index, source in enumerate(source_items, 1):
        source_id = str(source[source_id_key])
        row = dict(rows_by_source.get(source_id) or {})
        row[judgement_id_key] = f"{prefix}{index}"
        row[source_id_key] = source_id
        row[source_text_key] = str(
            source.get(source_value_key)
            or source.get("canonical_meaning")
            or ""
        )
        target_ids = [
            v for v in row.get(target_ids_key, []) if v in target_by_id
        ]
        row[target_ids_key] = target_ids
        match = str(row.get("target_match") or "")
        if match and match not in target_text:
            match = _first_target_evidence(target_ids, target_by_id)
        row["target_match"] = match
        verdict = str(row.get("verdict") or "uncertain")
        if verdict not in allowed_verdicts:
            verdict = "uncertain"
        if (not match or not target_ids) and verdict not in {"missing", "uncertain"}:
            verdict = "uncertain"
        if verdict == "missing":
            row[target_ids_key] = []
            row["target_match"] = ""
        row["verdict"] = verdict
        row["explanation"] = str(
            row.get("explanation")
            or "结构修复无法恢复完整逐字证据，保守标记为 uncertain。"
        )
        if kind != "relation" and row.get("eval_unit_id") not in eval_ids:
            source_unit_id = str(source.get("source_unit_id") or "")
            row["eval_unit_id"] = next(
                (
                    str(u["eval_unit_id"])
                    for u in eval_units
                    if source_unit_id in u.get("source_unit_ids", [])
                ),
                str(eval_units[0]["eval_unit_id"]),
            )
        output_rows.append(row)

    return {
        **artifact,
        list_key: output_rows,
        assessment_key: str(
            artifact.get(assessment_key) or "存在结构修复项，建议人工复核。"
        ),
    }


def _first_target_evidence(
    target_ids: list[str], target_by_id: dict[str, dict[str, Any]]
) -> str:
    for tid in target_ids:
        item = target_by_id[tid]
        span = item.get("evidence_span")
        if isinstance(span, str) and span:
            return span
        spans = item.get("evidence_spans")
        if isinstance(spans, list):
            for v in spans:
                if isinstance(v, str) and v:
                    return v
    return ""
