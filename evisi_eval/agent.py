from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
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


PROTOCOL_VERSION = "evisi_eval_v0.3"
MAX_REPAIR_ATTEMPTS = 2
ArtifactSink = Callable[[str, dict[str, Any]], None]


@dataclass
class StageResult:
    artifact: dict[str, Any]
    traces: list[dict[str, Any]]
    initial_issues: list[str]
    fallback_used: bool


class StageRunner:
    def __init__(self, client: LLMClient):
        self.client = client

    def run(
        self,
        stage_name: str,
        payload: dict[str, Any],
        validator: Callable[[dict[str, Any]], list[str]],
        fallback: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> StageResult:
        response = self.client.generate_json(load_prompt(stage_name), payload, task=stage_name)
        traces = [_trace(stage_name, response)]
        artifact = _canonicalize(stage_name, response.data, payload)
        initial_issues = validator(artifact)
        issues = list(initial_issues)

        for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
            if not issues:
                break
            repair_payload = {
                "stage_name": stage_name,
                "stage_input": payload,
                "validation_issues": issues,
                "repair_attempt": attempt,
                "json_to_repair": artifact,
            }
            repair = self.client.generate_json(
                load_prompt("schema_repair"), repair_payload, task=f"repair_{stage_name}"
            )
            traces.append(_trace(f"repair_{stage_name}", repair))
            artifact = _canonicalize(stage_name, repair.data, payload)
            issues = validator(artifact)

        fallback_used = False
        if issues and fallback is not None:
            artifact = _canonicalize(stage_name, fallback(artifact), payload)
            issues = validator(artifact)
            fallback_used = True
            traces.append(
                {
                    "task": f"fallback_{stage_name}",
                    "provider": "deterministic",
                    "model": "local",
                    "request_id": None,
                    "usage": {},
                }
            )
        if issues:
            raise ValueError(f"{stage_name} failed deterministic validation: {'; '.join(issues)}")
        return StageResult(artifact, traces, initial_issues, fallback_used)


def build_source_card(
    sample: dict[str, Any], client: LLMClient, sink: ArtifactSink | None = None
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    sample_id = _required(sample, "sample_id")
    source_text = _required(sample, "source_text")
    runner = StageRunner(client)
    artifacts: dict[str, dict[str, Any]] = {}
    all_traces: list[dict[str, Any]] = []
    validation: dict[str, Any] = {}

    base = {
        "sample_id": sample_id,
        "source_text": source_text,
        "src_lang": sample.get("src_lang", "unspecified"),
        "tgt_lang": sample.get("tgt_lang", "unspecified"),
        "domain": sample.get("domain", "unspecified"),
    }
    units_result = runner.run(
        "source_sentence_segmentation",
        base,
        lambda artifact: validate_source_units(artifact, source_text),
        fallback=lambda _: {
            "sample_id": sample_id,
            "source_units": [{"source_unit_id": "S1", "source_unit": source_text}],
        },
    )
    source_units = units_result.artifact["source_units"]
    _capture("source_01_units", units_result, artifacts, all_traces, validation, sink)

    anchors_result = runner.run(
        "source_anchor_extraction",
        {"sample_id": sample_id, "source_units": source_units},
        lambda artifact: validate_anchor_extraction(artifact, source_units, True),
        fallback=lambda artifact: _salvage_items(
            artifact, "source_anchors", source_units, "source_unit_id", "source_unit",
            "source_anchor_id", "SA", ("anchor_text", "normalized_meaning")
        ),
    )
    source_anchors = anchors_result.artifact["source_anchors"]
    _capture("source_02_anchors", anchors_result, artifacts, all_traces, validation, sink)

    events_result = runner.run(
        "source_event_extraction",
        {"sample_id": sample_id, "source_units": source_units},
        lambda artifact: validate_event_extraction(artifact, source_units, True),
        fallback=lambda artifact: _salvage_items(
            artifact, "source_events", source_units, "source_unit_id", "source_unit",
            "source_event_id", "SE", ("event_text", "canonical_meaning")
        ),
    )
    source_events = events_result.artifact["source_events"]
    _capture("source_03_events", events_result, artifacts, all_traces, validation, sink)

    relations_result = runner.run(
        "source_relation_extraction",
        {"sample_id": sample_id, "source_units": source_units, "source_events": source_events},
        lambda artifact: validate_relation_extraction(
            artifact, source_units, source_events, True
        ),
        fallback=lambda artifact: _salvage_relations(
            artifact, source_units, source_events, True
        ),
    )
    source_relations = relations_result.artifact["source_relations"]
    _capture("source_04_relations", relations_result, artifacts, all_traces, validation, sink)

    card = {
        "sample_id": sample_id,
        "source_text": source_text,
        "reference_translation": sample.get("reference_translation"),
        "src_lang": sample.get("src_lang", "unspecified"),
        "tgt_lang": sample.get("tgt_lang", "unspecified"),
        "domain": sample.get("domain", "unspecified"),
        "source_units": source_units,
        "source_anchors": source_anchors,
        "source_events": source_events,
        "source_relations": source_relations,
        "metadata": {
            "protocol_version": PROTOCOL_VERSION,
            "provider": client.provider_name,
            "model": client.model_name,
            "system_outputs_visible": False,
            "reference_translation_used": False,
            "validation": validation,
            "agent_trace": all_traces,
            "prompt_hashes": prompt_manifest(),
        },
    }
    card["metadata"]["source_card_hash"] = _artifact_hash(card)
    artifacts["source_cards"] = card
    if sink:
        sink("source_cards", card)
    return card, artifacts


def evaluate_system(
    source_card: dict[str, Any], output: dict[str, Any], client: LLMClient,
    sink: ArtifactSink | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    sample_id = _required(output, "sample_id")
    system_name = _required(output, "system_name")
    translation = _required(output, "si_translation")
    if sample_id != source_card["sample_id"]:
        raise ValueError("system output sample_id does not match source_card")

    runner = StageRunner(client)
    artifacts: dict[str, dict[str, Any]] = {}
    all_traces: list[dict[str, Any]] = []
    validation: dict[str, Any] = {}
    anonymous = "anonymous_system"
    source_units = source_card["source_units"]

    segmentation = runner.run(
        "target_aligned_segmentation",
        {
            "sample_id": sample_id,
            "system_name": anonymous,
            "si_translation": translation,
            "source_units": source_units,
        },
        lambda artifact: validate_eval_units(artifact, source_units, translation),
        fallback=lambda _: {
            "sample_id": sample_id,
            "system_name": anonymous,
            "eval_units": [
                {
                    "eval_unit_id": "E1",
                    "source_unit_ids": [row["source_unit_id"] for row in source_units],
                    "target_unit": translation,
                    "alignment_status": "uncertain",
                    "reason": "结构修复失败后保留完整双侧文本，等待人工复核",
                }
            ],
        },
    )
    eval_units = segmentation.artifact["eval_units"]
    _capture_target("target_01_eval_units", segmentation, system_name, artifacts, all_traces, validation, sink)

    target_view = [
        {"eval_unit_id": row["eval_unit_id"], "target_unit": row["target_unit"]}
        for row in eval_units
    ]
    target_anchors_result = runner.run(
        "target_anchor_extraction",
        {"sample_id": sample_id, "system_name": anonymous, "eval_units": target_view},
        lambda artifact: validate_anchor_extraction(artifact, target_view, False),
        fallback=lambda artifact: _salvage_items(
            artifact, "target_anchors", target_view, "eval_unit_id", "target_unit",
            "target_anchor_id", "TA", ("anchor_text", "normalized_meaning")
        ),
    )
    target_anchors = target_anchors_result.artifact["target_anchors"]
    _capture_target("target_02_anchors", target_anchors_result, system_name, artifacts, all_traces, validation, sink)

    target_events_result = runner.run(
        "target_event_extraction",
        {"sample_id": sample_id, "system_name": anonymous, "eval_units": target_view},
        lambda artifact: validate_event_extraction(artifact, target_view, False),
        fallback=lambda artifact: _salvage_items(
            artifact, "target_events", target_view, "eval_unit_id", "target_unit",
            "target_event_id", "TE", ("event_text", "canonical_meaning")
        ),
    )
    target_events = target_events_result.artifact["target_events"]
    _capture_target("target_03_events", target_events_result, system_name, artifacts, all_traces, validation, sink)

    target_relations_result = runner.run(
        "target_relation_extraction",
        {
            "sample_id": sample_id,
            "system_name": anonymous,
            "eval_units": target_view,
            "target_events": target_events,
        },
        lambda artifact: validate_relation_extraction(
            artifact, target_view, target_events, False
        ),
        fallback=lambda artifact: _salvage_relations(
            artifact, target_view, target_events, False
        ),
    )
    target_relations = target_relations_result.artifact["target_relations"]
    _capture_target("target_04_relations", target_relations_result, system_name, artifacts, all_traces, validation, sink)

    fluency_result = runner.run(
        "fluency_evaluation",
        {"sample_id": sample_id, "system_name": anonymous, "si_translation": translation},
        lambda artifact: validate_issue_evaluation(
            artifact, translation, "fluency_issues", "fluency_assessment", "F"
        ),
    )
    _capture_target("target_05_fluency", fluency_result, system_name, artifacts, all_traces, validation, sink)

    expression_result = runner.run(
        "si_expression_evaluation",
        {
            "sample_id": sample_id,
            "system_name": anonymous,
            "source_text": source_card["source_text"],
            "si_translation": translation,
        },
        lambda artifact: validate_issue_evaluation(
            artifact, translation, "si_expression_issues", "si_expression_assessment", "X"
        ),
    )
    _capture_target("target_06_si_expression", expression_result, system_name, artifacts, all_traces, validation, sink)

    target_card = {
        "sample_id": sample_id,
        "system_name": system_name,
        "si_translation": translation,
        "eval_units": eval_units,
        "target_anchors": target_anchors,
        "target_events": target_events,
        "target_relations": target_relations,
        "fluency_issues": fluency_result.artifact["fluency_issues"],
        "fluency_assessment": fluency_result.artifact["fluency_assessment"],
        "si_expression_issues": expression_result.artifact["si_expression_issues"],
        "si_expression_assessment": expression_result.artifact["si_expression_assessment"],
        "metadata": {
            "protocol_version": PROTOCOL_VERSION,
            "provider": client.provider_name,
            "model": client.model_name,
            "system_name_visible_to_agents": False,
            "reference_translation_used": False,
            "validation": validation,
        },
    }
    artifacts["target_eval_cards"] = target_card
    if sink:
        sink("target_eval_cards", target_card)

    anchor_result = runner.run(
        "anchor_judgement",
        {
            "sample_id": sample_id,
            "system_name": anonymous,
            "source_units": source_units,
            "eval_units": eval_units,
            "source_anchors": source_card["source_anchors"],
            "target_anchors": target_anchors,
        },
        lambda artifact: validate_judgements(
            artifact, source_card["source_anchors"], target_anchors, eval_units, "anchor"
        ),
        fallback=lambda artifact: _salvage_judgements(
            artifact, source_card["source_anchors"], target_anchors, eval_units, "anchor"
        ),
    )
    _capture_target("score_01_anchor_judgements", anchor_result, system_name, artifacts, all_traces, validation, sink)

    event_result = runner.run(
        "event_judgement",
        {
            "sample_id": sample_id,
            "system_name": anonymous,
            "source_units": source_units,
            "eval_units": eval_units,
            "source_events": source_card["source_events"],
            "target_events": target_events,
        },
        lambda artifact: validate_judgements(
            artifact, source_card["source_events"], target_events, eval_units, "event"
        ),
        fallback=lambda artifact: _salvage_judgements(
            artifact, source_card["source_events"], target_events, eval_units, "event"
        ),
    )
    _capture_target("score_02_event_judgements", event_result, system_name, artifacts, all_traces, validation, sink)

    relation_result = runner.run(
        "relation_judgement",
        {
            "sample_id": sample_id,
            "system_name": anonymous,
            "eval_units": eval_units,
            "source_relations": source_card["source_relations"],
            "target_relations": target_relations,
            "source_events": source_card["source_events"],
            "target_events": target_events,
        },
        lambda artifact: validate_judgements(
            artifact, source_card["source_relations"], target_relations, eval_units, "relation"
        ),
        fallback=lambda artifact: _salvage_judgements(
            artifact, source_card["source_relations"], target_relations, eval_units, "relation"
        ),
    )
    _capture_target("score_03_relation_judgements", relation_result, system_name, artifacts, all_traces, validation, sink)

    global_result = runner.run(
        "global_fidelity_review",
        {
            "sample_id": sample_id,
            "system_name": anonymous,
            "source_text": source_card["source_text"],
            "si_translation": translation,
            "source_units": source_units,
            "eval_units": eval_units,
            "anchor_judgements": anchor_result.artifact["anchor_judgements"],
            "event_judgements": event_result.artifact["event_judgements"],
            "relation_judgements": relation_result.artifact["relation_judgements"],
            "si_expression_issues": expression_result.artifact["si_expression_issues"],
        },
        validate_global_review,
    )
    _capture_target("score_04_global_review", global_result, system_name, artifacts, all_traces, validation, sink)

    scoring_payload = {
        "sample_id": sample_id,
        "system_name": anonymous,
        "anchor_judgements": anchor_result.artifact["anchor_judgements"],
        "event_judgements": event_result.artifact["event_judgements"],
        "relation_judgements": relation_result.artifact["relation_judgements"],
        "fluency_issues": fluency_result.artifact["fluency_issues"],
        "fluency_assessment": fluency_result.artifact["fluency_assessment"],
        "si_expression_issues": expression_result.artifact["si_expression_issues"],
        "si_expression_assessment": expression_result.artifact["si_expression_assessment"],
        "global_fidelity_review": global_result.artifact["global_fidelity_review"],
    }
    scores_result = runner.run("dimension_scoring", scoring_payload, validate_dimension_scores)
    _capture_target("score_05_dimension_scores", scores_result, system_name, artifacts, all_traces, validation, sink)
    scores = scores_result.artifact["dimension_scores"]
    final_score = weighted_score(scores)

    summary_result = runner.run(
        "final_summary",
        {
            **scoring_payload,
            "dimension_scores": scores,
            "dimension_score_explanations": scores_result.artifact["dimension_score_explanations"],
            "dimension_weights": DIMENSION_WEIGHTS,
            "final_score": final_score,
        },
        lambda artifact: validate_final_summary(artifact, final_score),
    )
    _capture_target("score_06_final_results", summary_result, system_name, artifacts, all_traces, validation, None)

    final_result = {
        "sample_id": sample_id,
        "system_name": system_name,
        "source_text": source_card["source_text"],
        "reference_translation": source_card.get("reference_translation"),
        "si_translation": translation,
        "source_card_hash": source_card["metadata"]["source_card_hash"],
        "source_units": source_units,
        "eval_units": eval_units,
        "source_anchors": source_card["source_anchors"],
        "target_anchors": target_anchors,
        "source_events": source_card["source_events"],
        "target_events": target_events,
        "source_relations": source_card["source_relations"],
        "target_relations": target_relations,
        "anchor_judgements": anchor_result.artifact["anchor_judgements"],
        "anchor_fidelity_assessment": anchor_result.artifact["anchor_fidelity_assessment"],
        "event_judgements": event_result.artifact["event_judgements"],
        "event_fidelity_assessment": event_result.artifact["event_fidelity_assessment"],
        "relation_judgements": relation_result.artifact["relation_judgements"],
        "relation_fidelity_assessment": relation_result.artifact["relation_fidelity_assessment"],
        "fluency_issues": fluency_result.artifact["fluency_issues"],
        "fluency_assessment": fluency_result.artifact["fluency_assessment"],
        "si_expression_issues": expression_result.artifact["si_expression_issues"],
        "si_expression_assessment": expression_result.artifact["si_expression_assessment"],
        "global_fidelity_review": global_result.artifact["global_fidelity_review"],
        "dimension_scores": scores,
        "dimension_score_explanations": scores_result.artifact["dimension_score_explanations"],
        "dimension_weights": DIMENSION_WEIGHTS,
        "final_score": final_score,
        "score_summary": summary_result.artifact["score_summary"],
        "metadata": {
            "protocol_version": PROTOCOL_VERSION,
            "provider": client.provider_name,
            "model": client.model_name,
            "system_name_visible_to_agents": False,
            "reference_translation_used": False,
            "validation": validation,
            "agent_trace": all_traces,
            "prompt_hashes": prompt_manifest(),
        },
    }
    artifacts["score_06_final_results"] = final_result
    if sink:
        sink("score_06_final_results", final_result)
    return final_result, artifacts


def _capture(
    key: str, result: StageResult, artifacts: dict[str, dict[str, Any]], traces: list[dict[str, Any]],
    validation: dict[str, Any], sink: ArtifactSink | None,
) -> None:
    artifacts[key] = result.artifact
    traces.extend(result.traces)
    validation[key] = {
        "initial_issues": result.initial_issues,
        "fallback_used": result.fallback_used,
    }
    if sink:
        sink(key, result.artifact)


def _capture_target(
    key: str, result: StageResult, system_name: str, artifacts: dict[str, dict[str, Any]],
    traces: list[dict[str, Any]], validation: dict[str, Any], sink: ArtifactSink | None,
) -> None:
    result.artifact["system_name"] = system_name
    _capture(key, result, artifacts, traces, validation, sink)


def _canonicalize(stage_name: str, raw: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    artifact = dict(raw) if isinstance(raw, dict) else {}
    if "sample_id" in payload:
        artifact["sample_id"] = payload["sample_id"]
    if "system_name" in payload:
        artifact["system_name"] = payload["system_name"]
    list_keys = {
        "source_sentence_segmentation": "source_units",
        "source_anchor_extraction": "source_anchors",
        "source_event_extraction": "source_events",
        "source_relation_extraction": "source_relations",
        "target_aligned_segmentation": "eval_units",
        "target_anchor_extraction": "target_anchors",
        "target_event_extraction": "target_events",
        "target_relation_extraction": "target_relations",
        "fluency_evaluation": "fluency_issues",
        "si_expression_evaluation": "si_expression_issues",
        "anchor_judgement": "anchor_judgements",
        "event_judgement": "event_judgements",
        "relation_judgement": "relation_judgements",
    }
    if stage_name in list_keys and not isinstance(artifact.get(list_keys[stage_name]), list):
        artifact[list_keys[stage_name]] = []
    if stage_name in {"source_relation_extraction", "target_relation_extraction"}:
        for relation in artifact.get(list_keys[stage_name], []):
            if isinstance(relation, dict) and "evidence_spans" not in relation:
                singular = relation.pop("evidence_span", None)
                relation["evidence_spans"] = [singular] if isinstance(singular, str) and singular else []
    return artifact


def _salvage_items(
    artifact: dict[str, Any], list_key: str, units: list[dict[str, Any]], unit_id_key: str,
    unit_text_key: str, item_id_key: str, prefix: str, required_fields: tuple[str, ...],
) -> dict[str, Any]:
    unit_by_id = {str(row.get(unit_id_key)): str(row.get(unit_text_key) or "") for row in units}
    kept = []
    for row in artifact.get(list_key, []):
        if not isinstance(row, dict):
            continue
        unit_id = str(row.get(unit_id_key) or "")
        evidence = str(row.get("evidence_span") or "")
        if unit_id not in unit_by_id or not evidence or evidence not in unit_by_id[unit_id]:
            continue
        if any(not str(row.get(key) or "").strip() for key in required_fields):
            continue
        row = dict(row)
        row[item_id_key] = f"{prefix}{len(kept) + 1}"
        kept.append(row)
    return {**artifact, list_key: kept}


def _salvage_relations(
    artifact: dict[str, Any], units: list[dict[str, Any]], events: list[dict[str, Any]],
    source_side: bool,
) -> dict[str, Any]:
    list_key = "source_relations" if source_side else "target_relations"
    relation_id_key = "source_relation_id" if source_side else "target_relation_id"
    prefix = "SR" if source_side else "TR"
    unit_ids_key = "source_unit_ids" if source_side else "eval_unit_ids"
    unit_id_key = "source_unit_id" if source_side else "eval_unit_id"
    unit_text_key = "source_unit" if source_side else "target_unit"
    related_key = "related_source_event_ids" if source_side else "related_target_event_ids"
    event_id_key = "source_event_id" if source_side else "target_event_id"
    unit_by_id = {str(row.get(unit_id_key)): str(row.get(unit_text_key) or "") for row in units}
    unit_order = {key: index for index, key in enumerate(unit_by_id)}
    event_ids = {str(row.get(event_id_key)) for row in events}
    kept = []
    for row in artifact.get(list_key, []):
        if not isinstance(row, dict):
            continue
        selected_ids = [item for item in row.get(unit_ids_key, []) if isinstance(item, str)]
        indexes = [unit_order[item] for item in selected_ids if item in unit_order]
        evidence = [item for item in row.get("evidence_spans", []) if isinstance(item, str) and item]
        selected_texts = [unit_by_id[item] for item in selected_ids if item in unit_by_id]
        if (
            not selected_ids
            or len(indexes) != len(selected_ids)
            or indexes != list(range(min(indexes), max(indexes) + 1))
            or not evidence
            or any(not any(span in text for text in selected_texts) for span in evidence)
            or any(item not in event_ids for item in row.get(related_key, []))
            or not str(row.get("relation_text") or "").strip()
            or not str(row.get("relation_meaning") or "").strip()
        ):
            continue
        row = dict(row)
        row[relation_id_key] = f"{prefix}{len(kept) + 1}"
        kept.append(row)
    return {**artifact, list_key: kept}


def _salvage_judgements(
    artifact: dict[str, Any], source_items: list[dict[str, Any]], target_items: list[dict[str, Any]],
    eval_units: list[dict[str, Any]], kind: str,
) -> dict[str, Any]:
    config = {
        "anchor": ("anchor_judgements", "anchor_judgement_id", "AJ", "source_anchor_id", "source_anchor", "anchor_text", "target_anchor_ids", "target_anchor_id", {"correct", "partially_correct", "incorrect", "missing", "uncertain"}, "anchor_fidelity_assessment"),
        "event": ("event_judgements", "event_judgement_id", "EJ", "source_event_id", "source_event", "event_text", "target_event_ids", "target_event_id", {"correct", "partially_correct", "incorrect", "missing", "uncertain"}, "event_fidelity_assessment"),
        "relation": ("relation_judgements", "relation_judgement_id", "RJ", "source_relation_id", "source_relation", "relation_text", "target_relation_ids", "target_relation_id", {"correct", "weakened", "incorrect", "missing", "uncertain"}, "relation_fidelity_assessment"),
    }[kind]
    (list_key, judgement_id_key, prefix, source_id_key, source_text_key, source_value_key,
     target_ids_key, target_id_key, allowed_verdicts, assessment_key) = config
    rows_by_source = {
        str(row.get(source_id_key)): row
        for row in artifact.get(list_key, []) if isinstance(row, dict) and row.get(source_id_key)
    }
    target_by_id = {str(row.get(target_id_key)): row for row in target_items}
    target_text = "".join(str(row.get("target_unit") or "") for row in eval_units)
    eval_ids = {str(row.get("eval_unit_id")) for row in eval_units}
    output_rows = []
    for index, source in enumerate(source_items, 1):
        source_id = str(source[source_id_key])
        row = dict(rows_by_source.get(source_id) or {})
        row[judgement_id_key] = f"{prefix}{index}"
        row[source_id_key] = source_id
        row[source_text_key] = str(source.get(source_value_key) or source.get("canonical_meaning") or "")
        target_ids = [value for value in row.get(target_ids_key, []) if value in target_by_id]
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
            row.get("explanation") or "结构修复无法恢复完整逐字证据，保守标记为 uncertain。"
        )
        if kind != "relation" and row.get("eval_unit_id") not in eval_ids:
            source_unit_id = str(source.get("source_unit_id") or "")
            row["eval_unit_id"] = next(
                (
                    str(unit["eval_unit_id"])
                    for unit in eval_units if source_unit_id in unit.get("source_unit_ids", [])
                ),
                str(eval_units[0]["eval_unit_id"]),
            )
        output_rows.append(row)
    return {
        **artifact,
        list_key: output_rows,
        assessment_key: str(artifact.get(assessment_key) or "存在结构修复项，建议人工复核。"),
    }


def _first_target_evidence(
    target_ids: list[str], target_by_id: dict[str, dict[str, Any]]
) -> str:
    for target_id in target_ids:
        item = target_by_id[target_id]
        span = item.get("evidence_span")
        if isinstance(span, str) and span:
            return span
        spans = item.get("evidence_spans")
        if isinstance(spans, list):
            for value in spans:
                if isinstance(value, str) and value:
                    return value
    return ""


def _trace(task: str, response: LLMResponse) -> dict[str, Any]:
    return {
        "task": task,
        "provider": response.provider,
        "model": response.model,
        "request_id": response.request_id,
        "usage": response.usage,
    }


def _required(row: dict[str, Any], key: str) -> str:
    value = str(row.get(key) or "")
    if not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _artifact_hash(artifact: dict[str, Any]) -> str:
    payload = {key: value for key, value in artifact.items() if key != "metadata"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
