"""EviSI-Eval v0.5 evidence agents and adjudication workflow."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable

from .llm_provider import LLMClient, LLMResponse
from .prompt_loader import load_prompt, prompt_manifest
from .validation import (
    MIN_FINAL_CONFIDENCE,
    PROTOCOL_VERSION,
    calculate_scores,
    validate_adjudication_artifact,
    validate_alignment_artifact,
    validate_delivery_artifact,
    validate_judgement_artifact,
    validate_source_card_artifact,
    validate_summary_artifact,
    validate_target_evidence_artifact,
)


MAX_REPAIR_ATTEMPTS = 2
ArtifactSink = Callable[[str, dict[str, Any]], None]
ArtifactNormalizer = Callable[[dict[str, Any]], tuple[dict[str, Any], list[str]]]


@dataclass
class StageResult:
    artifact: dict[str, Any]
    traces: list[dict[str, Any]]
    initial_issues: list[str]
    normalization_notes: list[str]


class Runner:
    """Run one semantic agent and allow two structure-only repair attempts."""

    def __init__(self, client: LLMClient):
        self.client = client

    def run(
        self,
        prompt_name: str,
        payload: dict[str, Any],
        validator: Callable[[dict[str, Any]], list[str]],
        fallback: Callable[[], dict[str, Any]] | None = None,
        normalizer: ArtifactNormalizer | None = None,
    ) -> StageResult:
        response = self.client.generate_json(load_prompt(prompt_name), payload, task=prompt_name)
        artifact = _canonicalize(response.data, payload)
        normalization_notes: list[str] = []
        if normalizer is not None:
            artifact, notes = normalizer(artifact)
            normalization_notes.extend(notes)
        traces = [_trace(prompt_name, response)]
        initial_issues = validator(artifact)
        issues = list(initial_issues)
        for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
            if not issues:
                break
            repair = self.client.generate_json(
                load_prompt("schema_repair"),
                {
                    "stage_name": prompt_name,
                    "stage_input": payload,
                    "validation_issues": issues,
                    "repair_attempt": attempt,
                    "json_to_repair": artifact,
                },
                task=f"repair_{prompt_name}",
            )
            traces.append(_trace(f"repair_{prompt_name}", repair))
            artifact = _canonicalize(repair.data, payload)
            if normalizer is not None:
                artifact, notes = normalizer(artifact)
                normalization_notes.extend(notes)
            issues = validator(artifact)
        if issues and fallback is not None:
            artifact = _canonicalize(fallback(), payload)
            issues = validator(artifact)
            traces.append(_local_trace(f"fallback_{prompt_name}"))
        if issues:
            raise ValueError(f"{prompt_name} failed validation: {'; '.join(issues)}")
        return StageResult(artifact, traces, initial_issues, normalization_notes)


class SourceCardAgent:
    """Build a source-only evaluation card once, before any system output is evaluated."""

    def __init__(self, client: LLMClient):
        self.client = client
        self.runner = Runner(client)

    def build(self, sample: dict[str, Any]) -> tuple[dict[str, Any], StageResult]:
        sample_id = _required(sample, "sample_id")
        source_text = _required(sample, "source_text")
        payload = {
            "sample_id": sample_id,
            "source_text": source_text,
            "src_lang": sample.get("src_lang", "unspecified"),
            "tgt_lang": sample.get("tgt_lang", "unspecified"),
            "domain": sample.get("domain", "unspecified"),
        }
        result = self.runner.run(
            "source_evidence_agent",
            payload,
            lambda artifact: validate_source_card_artifact(artifact, source_text),
        )
        card = {
            "sample_id": sample_id,
            "source_text": source_text,
            "reference_translation": sample.get("reference_translation"),
            "src_lang": sample.get("src_lang", "unspecified"),
            "tgt_lang": sample.get("tgt_lang", "unspecified"),
            "domain": sample.get("domain", "unspecified"),
            "source_units": _records(result.artifact.get("source_units")),
            "source_anchors": _records(result.artifact.get("source_anchors")),
            "source_events": _records(result.artifact.get("source_events")),
            "source_relations": _records(result.artifact.get("source_relations")),
            "metadata": {
                "protocol_version": PROTOCOL_VERSION,
                "provider": self.client.provider_name,
                "model": self.client.model_name,
                "frozen_before_system_evaluation": True,
                "system_outputs_visible": False,
                "reference_translation_used": False,
                "initial_validation_issues": result.initial_issues,
                "agent_trace": result.traces,
                "prompt_hashes": prompt_manifest(),
            },
        }
        card["metadata"]["source_card_hash"] = _artifact_hash(card)
        return card, result


class AlignmentAgent:
    def __init__(self, client: LLMClient):
        self.runner = Runner(client)

    def align(self, source_card: dict[str, Any], output: dict[str, Any]) -> StageResult:
        translation = _required(output, "si_translation")
        payload = {
            "sample_id": source_card["sample_id"],
            "system_name": "anonymous_system",
            "source_units": source_card["source_units"],
            "si_translation": translation,
        }
        return self.runner.run(
            "alignment_agent",
            payload,
            lambda artifact: validate_alignment_artifact(
                artifact, source_card["source_units"], translation
            ),
        )


class TargetEvidenceAgent:
    """Extract target semantics without receiving source text or source analysis."""

    def __init__(self, client: LLMClient):
        self.runner = Runner(client)

    def analyze(self, sample_id: str, eval_units: list[dict[str, Any]]) -> StageResult:
        target_units = [
            {"eval_unit_id": row["eval_unit_id"], "target_unit": row.get("target_unit", "")}
            for row in eval_units
        ]
        payload = {
            "sample_id": sample_id,
            "system_name": "anonymous_system",
            "target_units": target_units,
        }
        return self.runner.run(
            "target_evidence_agent",
            payload,
            lambda artifact: validate_target_evidence_artifact(artifact, target_units),
            normalizer=lambda artifact: _normalize_target_evidence(artifact, target_units),
        )


class FluencyAgent:
    def __init__(self, client: LLMClient):
        self.runner = Runner(client)

    def evaluate(self, sample_id: str, translation: str) -> StageResult:
        payload = {
            "sample_id": sample_id,
            "system_name": "anonymous_system",
            "si_translation": translation,
        }
        return self.runner.run(
            "fluency_agent",
            payload,
            lambda artifact: validate_delivery_artifact(
                artifact, translation, "fluency_issues", "fluency_assessment", "F"
            ),
        )


class SIExpressionAgent:
    def __init__(self, client: LLMClient):
        self.runner = Runner(client)

    def evaluate(self, source_card: dict[str, Any], translation: str) -> StageResult:
        payload = {
            "sample_id": source_card["sample_id"],
            "system_name": "anonymous_system",
            "source_text": source_card["source_text"],
            "si_translation": translation,
        }
        return self.runner.run(
            "si_expression_agent",
            payload,
            lambda artifact: validate_delivery_artifact(
                artifact, translation, "si_expression_issues", "si_expression_assessment", "X"
            ),
        )


class JudgeAgent:
    def __init__(self, client: LLMClient, prompt_name: str):
        self.runner = Runner(client)
        self.prompt_name = prompt_name

    def judge(self, source_card: dict[str, Any], target_card: dict[str, Any]) -> StageResult:
        payload = {
            "sample_id": source_card["sample_id"],
            "source_card": _source_view(source_card),
            "target_eval_card": _target_view(target_card),
        }
        return self.runner.run(
            self.prompt_name,
            payload,
            lambda artifact: validate_judgement_artifact(artifact, source_card, target_card),
        )


class AdjudicatorAgent:
    def __init__(self, client: LLMClient):
        self.runner = Runner(client)

    def adjudicate(
        self, source_card: dict[str, Any], target_card: dict[str, Any],
        disagreement_cases: list[dict[str, Any]],
    ) -> StageResult:
        disagreement_ids = {str(row["judgement_id"]) for row in disagreement_cases}
        payload = {
            "sample_id": source_card["sample_id"],
            "source_card": _source_view(source_card),
            "target_eval_card": _target_view(target_card),
            "disagreement_cases": disagreement_cases,
        }
        return self.runner.run(
            "adjudicator_agent",
            payload,
            lambda artifact: validate_adjudication_artifact(
                artifact, disagreement_ids, source_card, target_card
            ),
        )


class SummaryAgent:
    def __init__(self, client: LLMClient):
        self.runner = Runner(client)

    def summarize(self, payload: dict[str, Any]) -> StageResult:
        return self.runner.run(
            "summary_agent",
            payload,
            validate_summary_artifact,
            fallback=lambda: {
                "score_summary": {
                    "overall_judgement": "自动总结不可用，请直接查看结构化判定和计分诊断。",
                    "main_strengths": [],
                    "main_errors": [],
                    "uncertain_points": ["总结阶段结构修复失败。"],
                }
            },
        )


class EvaluationAgentLoop:
    """Evaluate one target against an already frozen source card."""

    def __init__(self, primary_client: LLMClient, review_client: LLMClient):
        self.primary_client = primary_client
        self.review_client = review_client
        self.alignment_agent = AlignmentAgent(primary_client)
        self.target_agent = TargetEvidenceAgent(primary_client)
        self.fluency_agent = FluencyAgent(primary_client)
        self.expression_agent = SIExpressionAgent(primary_client)
        self.primary_judge = JudgeAgent(primary_client, "primary_judge_agent")
        self.reviewer = JudgeAgent(review_client, "reviewer_agent")
        self.adjudicator = AdjudicatorAgent(review_client)
        self.summary_agent = SummaryAgent(primary_client)

    def run(
        self, source_card: dict[str, Any], output: dict[str, Any],
        target_sink: ArtifactSink | None = None, score_sink: ArtifactSink | None = None,
        cached_target_card: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        sample_id = _required(output, "sample_id")
        system_name = _required(output, "system_name")
        translation = _required(output, "si_translation")
        if sample_id != source_card["sample_id"]:
            raise ValueError("system output sample_id does not match frozen source card")
        traces: list[dict[str, Any]] = []
        validation_log: dict[str, Any] = {}
        artifacts: dict[str, dict[str, Any]] = {}

        if cached_target_card is not None:
            target_card = dict(cached_target_card)
            traces.append(_local_trace("reuse_target_eval_card"))
            validation_log["target_eval_card_cache"] = {"reused": True}
        else:
            alignment = self.alignment_agent.align(source_card, output)
            traces.extend(alignment.traces)
            _log_validation("alignment_agent", alignment, validation_log)
            eval_units = _records(alignment.artifact.get("eval_units"))

            target = self.target_agent.analyze(sample_id, eval_units)
            traces.extend(target.traces)
            _log_validation("target_evidence_agent", target, validation_log)

            fluency = self.fluency_agent.evaluate(sample_id, translation)
            traces.extend(fluency.traces)
            _log_validation("fluency_agent", fluency, validation_log)

            expression = self.expression_agent.evaluate(source_card, translation)
            traces.extend(expression.traces)
            _log_validation("si_expression_agent", expression, validation_log)

            target_card = {
                "sample_id": sample_id,
                "system_name": system_name,
                "si_translation": translation,
                "eval_units": eval_units,
                "target_anchors": _records(target.artifact.get("target_anchors")),
                "target_events": _records(target.artifact.get("target_events")),
                "target_relations": _records(target.artifact.get("target_relations")),
                "fluency_issues": _records(fluency.artifact.get("fluency_issues")),
                "fluency_assessment": str(fluency.artifact.get("fluency_assessment") or ""),
                "si_expression_issues": _records(expression.artifact.get("si_expression_issues")),
                "si_expression_assessment": str(expression.artifact.get("si_expression_assessment") or ""),
                "metadata": {
                    "protocol_version": PROTOCOL_VERSION,
                    "system_name_visible_to_agents": False,
                    "reference_translation_used": False,
                    "primary_provider": self.primary_client.provider_name,
                    "primary_model": self.primary_client.model_name,
                    "validation": validation_log,
                },
            }
        artifacts["target_eval_cards"] = target_card
        if target_sink:
            target_sink("target_eval_cards", target_card)

        primary = self.primary_judge.judge(source_card, target_card)
        traces.extend(primary.traces)
        _log_validation("primary_judge_agent", primary, validation_log)
        artifacts["primary_judgements"] = primary.artifact
        if score_sink:
            score_sink("primary_judgements", _with_identity(primary.artifact, sample_id, system_name))

        review = self.reviewer.judge(source_card, target_card)
        traces.extend(review.traces)
        _log_validation("reviewer_agent", review, validation_log)
        artifacts["review_judgements"] = review.artifact
        if score_sink:
            score_sink("review_judgements", _with_identity(review.artifact, sample_id, system_name))

        disagreement_cases = _build_disagreement_cases(primary.artifact, review.artifact)
        adjudication_artifact: dict[str, Any] = {"adjudications": []}
        if disagreement_cases:
            adjudication = self.adjudicator.adjudicate(source_card, target_card, disagreement_cases)
            traces.extend(adjudication.traces)
            _log_validation("adjudicator_agent", adjudication, validation_log)
            adjudication_artifact = adjudication.artifact
            if score_sink:
                score_sink("adjudications", _with_identity(adjudication_artifact, sample_id, system_name))
        final_judgements = _merge_judgements(
            primary.artifact, review.artifact, adjudication_artifact
        )
        score = calculate_scores(
            final_judgements,
            target_card["fluency_issues"],
            target_card["si_expression_issues"],
            source_card,
        )
        summary_payload = {
            "sample_id": sample_id,
            "final_judgements": final_judgements,
            "fluency_issues": target_card["fluency_issues"],
            "si_expression_issues": target_card["si_expression_issues"],
            **score,
        }
        summary = self.summary_agent.summarize(summary_payload)
        traces.extend(summary.traces)
        _log_validation("summary_agent", summary, validation_log)

        result = {
            "sample_id": sample_id,
            "system_name": system_name,
            "source_text": source_card["source_text"],
            "reference_translation": source_card.get("reference_translation"),
            "si_translation": translation,
            "source_card_hash": source_card["metadata"]["source_card_hash"],
            "source_units": source_card["source_units"],
            "eval_units": target_card["eval_units"],
            "source_anchors": source_card["source_anchors"],
            "target_anchors": target_card["target_anchors"],
            "source_events": source_card["source_events"],
            "target_events": target_card["target_events"],
            "source_relations": source_card["source_relations"],
            "target_relations": target_card["target_relations"],
            **final_judgements,
            "fluency_issues": target_card["fluency_issues"],
            "fluency_assessment": target_card["fluency_assessment"],
            "si_expression_issues": target_card["si_expression_issues"],
            "si_expression_assessment": target_card["si_expression_assessment"],
            **score,
            "score_summary": summary.artifact["score_summary"],
            "review": {
                "review_provider": self.review_client.provider_name,
                "review_model": self.review_client.model_name,
                "independent_model": (
                    self.review_client.provider_name != self.primary_client.provider_name
                    or self.review_client.model_name != self.primary_client.model_name
                ),
                "disagreement_count": len(disagreement_cases),
                "adjudication_count": len(_records(adjudication_artifact.get("adjudications"))),
            },
            "metadata": {
                "protocol_version": PROTOCOL_VERSION,
                "system_name_visible_to_agents": False,
                "reference_translation_used": False,
                "validation": validation_log,
                "agent_trace": traces,
                "prompt_hashes": prompt_manifest(),
            },
        }
        artifacts["score_06_final_results"] = result
        if score_sink:
            score_sink("score_06_final_results", result)
        return result, artifacts


def _build_disagreement_cases(primary: dict[str, Any], review: dict[str, Any]) -> list[dict[str, Any]]:
    cases = []
    for kind in ("anchor", "event", "relation"):
        key = f"{kind}_judgements"
        review_by_id = {str(row.get("judgement_id")): row for row in _records(review.get(key))}
        for row in _records(primary.get(key)):
            judgement_id = str(row.get("judgement_id") or "")
            other = review_by_id.get(judgement_id)
            if other is None:
                continue
            if (
                row.get("verdict") != other.get("verdict")
                or float(row.get("confidence", 0)) < MIN_FINAL_CONFIDENCE
                or float(other.get("confidence", 0)) < MIN_FINAL_CONFIDENCE
            ):
                cases.append(
                    {
                        "judgement_id": judgement_id,
                        "kind": kind,
                        "primary": row,
                        "reviewer": other,
                    }
                )
    return cases


def _merge_judgements(
    primary: dict[str, Any], review: dict[str, Any], adjudication: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    adjudicated = {
        str(row.get("judgement_id")): row
        for row in _records(adjudication.get("adjudications"))
    }
    output: dict[str, list[dict[str, Any]]] = {}
    for kind in ("anchor", "event", "relation"):
        key = f"{kind}_judgements"
        reviewer_by_id = {str(row.get("judgement_id")): row for row in _records(review.get(key))}
        rows = []
        for primary_row in _records(primary.get(key)):
            judgement_id = str(primary_row.get("judgement_id") or "")
            review_row = reviewer_by_id[judgement_id]
            if judgement_id in adjudicated:
                final = dict(adjudicated[judgement_id])
                resolution = "adjudicated"
            else:
                final = dict(primary_row)
                final["confidence"] = round(
                    min(float(primary_row.get("confidence", 0)), float(review_row.get("confidence", 0))), 4
                )
                resolution = "primary_reviewer_agreement"
            final["review_verdict"] = review_row.get("verdict")
            final["review_confidence"] = review_row.get("confidence")
            final["resolution"] = resolution
            rows.append(final)
        output[key] = rows
    return output


def _source_view(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_units": card["source_units"],
        "source_anchors": card["source_anchors"],
        "source_events": card["source_events"],
        "source_relations": card["source_relations"],
    }


def _target_view(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "eval_units": card["eval_units"],
        "target_anchors": card["target_anchors"],
        "target_events": card["target_events"],
        "target_relations": card["target_relations"],
    }


def _canonicalize(raw: Any, payload: dict[str, Any]) -> dict[str, Any]:
    artifact = dict(raw) if isinstance(raw, dict) else {}
    for key in ("sample_id", "system_name"):
        if key in payload:
            artifact[key] = payload[key]
    return artifact


def _with_identity(artifact: dict[str, Any], sample_id: str, system_name: str) -> dict[str, Any]:
    return {"sample_id": sample_id, "system_name": system_name, **artifact}


def _log_validation(name: str, result: StageResult, log: dict[str, Any]) -> None:
    log[name] = {
        "initial_issues": result.initial_issues,
        "repair_count": max(0, len(result.traces) - 1),
        "normalization_notes": result.normalization_notes,
    }


def _normalize_target_evidence(
    artifact: dict[str, Any], target_units: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    normalized = dict(artifact)
    unit_by_id = {
        str(row.get("eval_unit_id")): str(row.get("target_unit") or "")
        for row in target_units
    }
    notes: list[str] = []
    for list_key, id_key, text_key in (
        ("target_anchors", "target_anchor_id", "anchor_text"),
        ("target_events", "target_event_id", "event_text"),
    ):
        rows = [dict(row) for row in _records(normalized.get(list_key))]
        normalized[list_key] = rows
        for row in rows:
            unit_text = unit_by_id.get(str(row.get("eval_unit_id") or ""), "")
            original = str(row.get("evidence_span") or "")
            if original and original in unit_text:
                continue
            replacement = _locate_verbatim(unit_text, original)
            if replacement is None:
                replacement = _locate_verbatim(unit_text, str(row.get(text_key) or ""))
            if replacement is not None:
                row["evidence_span"] = replacement
                notes.append(f"{row.get(id_key)} evidence_span mapped to verbatim target text")

    relation_rows = [dict(row) for row in _records(normalized.get("target_relations"))]
    normalized["target_relations"] = relation_rows
    for row in relation_rows:
        selected_texts = [
            unit_by_id.get(unit_id, "") for unit_id in _strings(row.get("eval_unit_ids"))
        ]
        spans = []
        changed = False
        for span in _strings(row.get("evidence_spans")):
            if any(span in text for text in selected_texts):
                spans.append(span)
                continue
            replacement = next(
                (
                    located for text in selected_texts
                    if (located := _locate_verbatim(text, span)) is not None
                ),
                None,
            )
            spans.append(replacement if replacement is not None else span)
            changed = changed or replacement is not None
        if changed:
            row["evidence_spans"] = spans
            notes.append(f"{row.get('target_relation_id')} evidence_spans mapped to verbatim target text")
    return normalized, notes


def _locate_verbatim(text: str, candidate: str) -> str | None:
    if not text or not candidate:
        return None
    if candidate in text:
        return candidate
    compact_text: list[str] = []
    positions: list[int] = []
    for index, character in enumerate(text):
        if not character.isspace():
            compact_text.append(character)
            positions.append(index)
    compact_candidate = "".join(character for character in candidate if not character.isspace())
    if not compact_candidate:
        return None
    start = "".join(compact_text).find(compact_candidate)
    if start < 0:
        return None
    end = start + len(compact_candidate) - 1
    return text[positions[start] : positions[end] + 1]


def _required(row: dict[str, Any], key: str) -> str:
    value = str(row.get(key) or "")
    if not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []


def _trace(task: str, response: LLMResponse) -> dict[str, Any]:
    return {
        "task": task,
        "provider": response.provider,
        "model": response.model,
        "request_id": response.request_id,
        "usage": response.usage,
    }


def _local_trace(task: str) -> dict[str, Any]:
    return {"task": task, "provider": "deterministic", "model": "local", "request_id": None, "usage": {}}


def _artifact_hash(artifact: dict[str, Any]) -> str:
    payload = {key: value for key, value in artifact.items() if key != "metadata"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
