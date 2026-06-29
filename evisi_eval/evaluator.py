from __future__ import annotations

from typing import Any

from .llm_provider import LLMClient, LLMResponse
from .prompt_loader import load_prompt
from .validation import (
    EFFICIENCY_TYPES,
    FLUENCY_TYPES,
    validate_alignment,
    validate_delivery,
    validate_sentence_alignment,
    validate_target_analysis,
)


EVALUATION_SCHEMA_VERSION = "0.4.1"

ANCHOR_OK = {"exact", "equivalent"}
EVENT_OK = {"covered", "compressed_covered"}
RELATION_OK = {"preserved"}

SENTENCE_ALIGNMENT_CONTRACT = {
    "target_units": [{"unit_id": "T1", "unit_text": "verbatim target unit"}],
    "sentence_alignments": [
        {
            "source_sentence_id": "S1",
            "source_sentence_text": "verbatim frozen source sentence",
            "target_unit_ids": ["T1"],
            "target_spans": ["verbatim target unit"],
            "alignment_type": "one_to_one|one_to_many|many_to_one|omitted|uncertain",
            "group_id": None,
            "confidence": 0.0,
            "reason": "semantic localization reason",
        }
    ],
    "unaligned_target_unit_ids": [],
}

TARGET_ANALYSIS_CONTRACT = {
    "target_units": [{"unit_id": "T1", "unit_text": "verbatim target text"}],
    "target_anchors": [
        {
            "target_anchor_id": "TA1",
            "unit_id": "T1",
            "target_span": "verbatim target span",
            "normalized_value": "canonical value",
            "anchor_type": "allowed anchor type",
            "attributes": {},
            "confidence": 0.0,
        }
    ],
    "target_events": [
        {
            "target_event_id": "TV1",
            "unit_ids": ["T1"],
            "evidence_spans": ["verbatim target evidence"],
            "canonical_meaning": "normalized event",
            "predicate": "normalized predicate",
            "arguments": [],
            "attributes": {},
            "confidence": 0.0,
        }
    ],
    "target_relations": [
        {
            "target_relation_id": "TR1",
            "relation_type": "allowed relation type",
            "head_target_event_id": "TV1",
            "dependent_target_event_id": "TV2",
            "target_cues": [],
            "canonical_meaning": "normalized relation",
            "confidence": 0.0,
        }
    ],
}


def evaluate_translation(
    card: dict[str, Any],
    system_name: str,
    si_translation: str,
    primary_client: LLMClient,
    review_client: LLMClient | None = None,
) -> dict[str, Any]:
    translation = str(si_translation or "").strip()
    if not translation:
        raise ValueError("si_translation must be non-empty")

    traces: list[dict[str, Any]] = []
    sentence_response = primary_client.generate_json(
        load_prompt("sentence_alignment"),
        {
            "source_text": card["source_text"],
            "source_sentences": card.get("sentences", []),
            "target_translation": translation,
            "source_language": card.get("src_lang"),
            "target_language": card.get("tgt_lang"),
        },
        task="align_source_and_target_sentences",
    )
    traces.append(_trace("align_source_and_target_sentences", sentence_response))
    sentence_alignment = _normalize_sentence_alignment(
        _unwrap(sentence_response.data, "sentence_alignment")
    )
    sentence_alignment, sentence_validation = _validate_or_repair(
        "sentence_alignment",
        sentence_alignment,
        validate_sentence_alignment(sentence_alignment, card.get("sentences", []), translation),
        primary_client,
        traces,
        {
            "source_sentences": card.get("sentences", []),
            "target_translation": translation,
            "required_output_contract": SENTENCE_ALIGNMENT_CONTRACT,
        },
        lambda artifact: validate_sentence_alignment(
            _normalize_sentence_alignment(artifact), card.get("sentences", []), translation
        ),
    )
    sentence_alignment = _normalize_sentence_alignment(sentence_alignment)

    target_response = primary_client.generate_json(
        load_prompt("target_analysis"),
        {
            "si_translation": translation,
            "target_language": card.get("tgt_lang"),
            "source_sentences": card.get("sentences", []),
            "source_anchors": card.get("anchors", []),
            "source_events": card.get("events", []),
            "source_relations": card.get("relations", []),
            "sentence_alignments": sentence_alignment["sentence_alignments"],
            "target_units": sentence_alignment["target_units"],
        },
        task="analyze_target_semantics",
    )
    traces.append(_trace("analyze_target_semantics", target_response))
    target_analysis = _normalize_target_analysis(_unwrap(target_response.data, "target_analysis"))
    target_analysis, target_validation = _validate_or_repair(
        "target_analysis",
        target_analysis,
        _target_analysis_issues(
            target_analysis, translation, sentence_alignment
        ),
        primary_client,
        traces,
        {
            "target_translation": translation,
            "source_sentences": card.get("sentences", []),
            "source_anchors": card.get("anchors", []),
            "source_events": card.get("events", []),
            "source_relations": card.get("relations", []),
            "sentence_alignments": sentence_alignment["sentence_alignments"],
            "frozen_target_units": sentence_alignment["target_units"],
            "required_output_contract": TARGET_ANALYSIS_CONTRACT,
        },
        lambda artifact: _target_analysis_issues(
            _normalize_target_analysis(artifact),
            translation,
            sentence_alignment,
        ),
    )
    target_analysis = _normalize_target_analysis(target_analysis)
    final_target_issues = _target_analysis_issues(
        target_analysis, translation, sentence_alignment
    )
    if final_target_issues:
        raise ValueError(
            "target_analysis failed frozen-unit validation: " + "; ".join(final_target_issues)
        )

    alignment_response = primary_client.generate_json(
        load_prompt("semantic_alignment"),
        {
            "source_card": card,
            "target_translation": translation,
            "sentence_alignment": sentence_alignment,
            "target_analysis": target_analysis,
            "offline_translation": card.get("offline_translation"),
        },
        task="align_source_and_target",
    )
    traces.append(_trace("align_source_and_target", alignment_response))
    alignment_raw = _unwrap(alignment_response.data, "alignment")
    raw_alignment_issues = validate_alignment(alignment_raw, card, translation)
    if raw_alignment_issues:
        alignment_raw, _ = _validate_or_repair(
            "semantic_alignment",
            alignment_raw,
            raw_alignment_issues,
            primary_client,
            traces,
            {"source_card": card, "target_translation": translation, "target_analysis": target_analysis},
            lambda artifact: validate_alignment(artifact, card, translation),
            fail_closed=False,
        )
    alignment = _normalize_alignment(alignment_raw, card, translation)

    delivery_response = primary_client.generate_json(
        load_prompt("target_delivery"),
        {"si_translation": translation, "target_language": card.get("tgt_lang")},
        task="evaluate_target_delivery",
    )
    traces.append(_trace("evaluate_target_delivery", delivery_response))
    delivery_raw = _unwrap(delivery_response.data, "target_delivery")
    delivery_issues = validate_delivery(delivery_raw, translation)
    if delivery_issues:
        delivery_raw, _ = _validate_or_repair(
            "target_delivery",
            delivery_raw,
            delivery_issues,
            primary_client,
            traces,
            {"target_translation": translation},
            lambda artifact: validate_delivery(artifact, translation),
            fail_closed=False,
        )
    delivery = _normalize_delivery(delivery_raw, translation)

    candidates = _candidate_errors(card, alignment, delivery)
    decisions = _review_errors(
        candidates, card, target_analysis, translation, review_client, traces
    )
    _attach_reviews(alignment, delivery, decisions)

    return {
        "sample_id": card["sample_id"],
        "system_name": system_name,
        "source_text": card["source_text"],
        "offline_translation": card.get("offline_translation"),
        "si_translation": translation,
        "evaluation_mode": "reference_assisted" if card.get("offline_translation") else "source_only",
        "card_hash": card.get("metadata", {}).get("card_hash"),
        "source_card": card,
        "sentence_alignment": sentence_alignment,
        "target_analysis": target_analysis,
        **alignment,
        **delivery,
        "agent_trace": traces,
        "metadata": {
            "schema_version": EVALUATION_SCHEMA_VERSION,
            "primary_provider": primary_client.provider_name,
            "primary_model": primary_client.model_name,
            "review_provider": review_client.provider_name if review_client else None,
            "review_model": review_client.model_name if review_client else None,
            "system_name_visible_to_agents": False,
            "system_asr_used": False,
            "sentence_alignment_validation_issues_before_repair": sentence_validation,
            "target_validation_issues_before_repair": target_validation,
            "alignment_validation_issues_before_repair": raw_alignment_issues,
            "delivery_validation_issues_before_repair": delivery_issues,
        },
    }


def _validate_or_repair(
    artifact_type: str,
    artifact: dict[str, Any],
    issues: list[str],
    client: LLMClient,
    traces: list[dict[str, Any]],
    context: dict[str, Any],
    validator: Any,
    fail_closed: bool = True,
) -> tuple[dict[str, Any], list[str]]:
    initial = list(issues)
    if not issues:
        return artifact, initial
    response = client.generate_json(
        load_prompt("schema_repair"),
        {
            "artifact_type": artifact_type,
            "validation_issues": issues,
            "json_to_repair": artifact,
            **context,
        },
        task=f"repair_{artifact_type}",
    )
    traces.append(_trace(f"repair_{artifact_type}", response))
    repaired = _unwrap(response.data, artifact_type)
    remaining = validator(repaired)
    if remaining and fail_closed:
        raise ValueError(f"{artifact_type} failed deterministic validation: {'; '.join(remaining)}")
    return (repaired if not remaining else artifact), initial


def _normalize_alignment(
    raw: dict[str, Any], card: dict[str, Any], translation: str
) -> dict[str, list[dict[str, Any]]]:
    specs = (
        ("anchor_alignments", "anchor_id", card.get("anchors", []), "ambiguous", {"exact", "equivalent", "incorrect", "missing", "ambiguous"}),
        ("event_alignments", "event_id", card.get("events", []), "ambiguous", {"covered", "compressed_covered", "partially_covered", "contradicted", "missing", "ambiguous"}),
        ("relation_alignments", "relation_id", card.get("relations", []), "ambiguous", {"preserved", "weakened", "reversed", "missing", "ambiguous"}),
    )
    output: dict[str, list[dict[str, Any]]] = {}
    for key, id_key, source_items, default, allowed in specs:
        by_id = {str(item.get(id_key)): item for item in _records(raw.get(key)) if item.get(id_key)}
        rows = []
        for source in _records(source_items):
            if not source.get("required", True):
                continue
            item_id = str(source[id_key])
            candidate = dict(by_id.get(item_id) or {})
            verdict = str(candidate.get("verdict") or default).strip().lower()
            if verdict not in allowed:
                verdict = default
            spans = _valid_spans(candidate.get("target_spans"), translation)
            if len(spans) != len(_strings(candidate.get("target_spans"))):
                verdict = "ambiguous"
            row = {
                **source,
                id_key: item_id,
                "target_anchor_ids": _strings(candidate.get("target_anchor_ids")),
                "target_event_ids": _strings(candidate.get("target_event_ids")),
                "target_unit_ids": _strings(candidate.get("target_unit_ids")),
                "target_spans": spans,
                "verdict": verdict,
                "confidence": _confidence(candidate.get("confidence")),
                "reason": str(candidate.get("reason") or "Model omitted a valid structured verdict"),
                "error_ref": f"{id_key}:{item_id}" if verdict not in _ok_verdicts(id_key) else None,
            }
            if id_key == "event_id":
                scope = str(candidate.get("error_scope") or "none").strip().lower()
                row["error_scope"] = scope if scope in {"none", "anchor_only", "event_only", "mixed"} else "none"
                row["attribute_errors"] = _strings(candidate.get("attribute_errors"))
            if id_key == "relation_id":
                row["independent_error"] = bool(candidate.get("independent_error", True))
            rows.append(row)
        output[key] = rows
    return output


def _normalize_sentence_alignment(raw: dict[str, Any]) -> dict[str, Any]:
    units = []
    for index, item in enumerate(_records(raw.get("target_units")), 1):
        units.append(
            {
                "unit_id": str(
                    item.get("unit_id") or item.get("target_unit_id") or item.get("id") or f"T{index}"
                ).strip(),
                "unit_text": str(
                    item.get("unit_text") or item.get("text") or item.get("target_span") or ""
                ).strip(),
            }
        )
    unit_text_by_id = {item["unit_id"]: item["unit_text"] for item in units}

    alignments = []
    raw_alignments = raw.get("sentence_alignments") or raw.get("alignments")
    for item in _records(raw_alignments):
        target_ids = _strings(item.get("target_unit_ids") or item.get("unit_ids"))
        supplied_spans = _strings(item.get("target_spans"))
        alignments.append(
            {
                "source_sentence_id": str(
                    item.get("source_sentence_id") or item.get("sentence_id") or ""
                ).strip(),
                "source_sentence_text": str(
                    item.get("source_sentence_text") or item.get("sentence_text") or ""
                ).strip(),
                "target_unit_ids": target_ids,
                "target_spans": supplied_spans
                or [unit_text_by_id[target_id] for target_id in target_ids if target_id in unit_text_by_id],
                "alignment_type": str(item.get("alignment_type") or item.get("type") or "").strip().lower(),
                "group_id": str(item.get("group_id") or "").strip() or None,
                "confidence": _confidence(item.get("confidence")),
                "reason": str(item.get("reason") or "").strip(),
            }
        )
    return {
        "target_units": units,
        "sentence_alignments": alignments,
        "unaligned_target_unit_ids": _strings(
            raw.get("unaligned_target_unit_ids") or raw.get("unaligned_unit_ids")
        ),
    }


def _target_analysis_issues(
    analysis: dict[str, Any], translation: str, sentence_alignment: dict[str, Any]
) -> list[str]:
    issues = validate_target_analysis(
        analysis, translation, sentence_alignment.get("target_units", [])
    )
    has_localized_semantics = any(
        item.get("alignment_type") in {"one_to_one", "one_to_many", "many_to_one"}
        and item.get("target_unit_ids")
        for item in sentence_alignment.get("sentence_alignments", [])
    )
    if (
        has_localized_semantics
        and not analysis.get("target_anchors")
        and not analysis.get("target_events")
    ):
        issues.append(
            "target analysis cannot be semantically empty when sentence alignment localized source meaning"
        )
    return issues


def _normalize_target_analysis(raw: dict[str, Any]) -> dict[str, Any]:
    units = []
    for index, item in enumerate(_records(raw.get("target_units")), 1):
        units.append(
            {
                "unit_id": str(
                    item.get("unit_id") or item.get("target_unit_id") or item.get("id") or f"T{index}"
                ).strip(),
                "unit_text": str(
                    item.get("unit_text") or item.get("text") or item.get("target_span") or ""
                ).strip(),
            }
        )

    anchors = []
    for index, item in enumerate(_records(raw.get("target_anchors")), 1):
        target_span = str(item.get("target_span") or item.get("anchor_text") or "").strip()
        anchors.append(
            {
                "target_anchor_id": str(
                    item.get("target_anchor_id") or item.get("anchor_id") or f"TA{index}"
                ).strip(),
                "unit_id": str(item.get("unit_id") or item.get("target_unit_id") or "").strip(),
                "target_span": target_span,
                "normalized_value": str(
                    item.get("normalized_value") or item.get("normalized_entity") or target_span
                ).strip(),
                "anchor_type": str(item.get("anchor_type") or item.get("entity_type") or "OTHER").strip().upper(),
                "attributes": item.get("attributes") if isinstance(item.get("attributes"), dict) else {},
                "confidence": _confidence(item.get("confidence")),
            }
        )

    events = []
    for index, item in enumerate(_records(raw.get("target_events")), 1):
        events.append(
            {
                "target_event_id": str(
                    item.get("target_event_id") or item.get("event_id") or f"TV{index}"
                ).strip(),
                "unit_ids": _strings(item.get("unit_ids") or item.get("target_unit_ids")),
                "evidence_spans": _strings(item.get("evidence_spans") or item.get("target_spans")),
                "canonical_meaning": str(item.get("canonical_meaning") or "").strip(),
                "predicate": str(item.get("predicate") or "").strip(),
                "arguments": _records(item.get("arguments")),
                "attributes": item.get("attributes") if isinstance(item.get("attributes"), dict) else {},
                "confidence": _confidence(item.get("confidence")),
            }
        )

    relations = []
    for index, item in enumerate(_records(raw.get("target_relations")), 1):
        relations.append(
            {
                "target_relation_id": str(
                    item.get("target_relation_id") or item.get("relation_id") or f"TR{index}"
                ).strip(),
                "relation_type": str(item.get("relation_type") or item.get("type") or "").strip().lower(),
                "head_target_event_id": str(
                    item.get("head_target_event_id") or item.get("head_event_id") or ""
                ).strip(),
                "dependent_target_event_id": str(
                    item.get("dependent_target_event_id") or item.get("dependent_event_id") or ""
                ).strip(),
                "target_cues": _strings(item.get("target_cues") or item.get("source_cues")),
                "canonical_meaning": str(item.get("canonical_meaning") or "").strip(),
                "confidence": _confidence(item.get("confidence")),
            }
        )
    return {
        "target_units": units,
        "target_anchors": anchors,
        "target_events": events,
        "target_relations": relations,
    }


def _normalize_delivery(raw: dict[str, Any], translation: str) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    for key in ("fluency_issues", "efficiency_issues"):
        allowed_types = FLUENCY_TYPES if key == "fluency_issues" else EFFICIENCY_TYPES
        rows = []
        seen: set[str] = set()
        for index, item in enumerate(_records(raw.get(key)), 1):
            span = str(item.get("target_span") or "").strip()
            if not span or span not in translation:
                continue
            issue_type = str(item.get("issue_type") or "").strip().lower()
            if issue_type not in allowed_types:
                continue
            issue_id = str(item.get("issue_id") or f"I{index}").strip()
            if issue_id in seen:
                continue
            seen.add(issue_id)
            severity = str(item.get("severity") or "minor").strip().lower()
            rows.append(
                {
                    "issue_id": issue_id,
                    "issue_type": issue_type,
                    "target_span": span,
                    "severity": severity if severity in {"minor", "major", "critical"} else "minor",
                    "confidence": _confidence(item.get("confidence")),
                    "reason": str(item.get("reason") or "Concrete target-language issue"),
                    "listener_impact": str(item.get("listener_impact") or "unspecified"),
                    "error_ref": f"issue_id:{issue_id}",
                }
            )
        output[key] = rows
    return output


def _candidate_errors(
    card: dict[str, Any], alignment: dict[str, Any], delivery: dict[str, Any]
) -> list[dict[str, Any]]:
    candidates = []
    dimensions = (
        ("anchor_accuracy", alignment["anchor_alignments"]),
        ("event_preservation", alignment["event_alignments"]),
        ("relation_preservation", alignment["relation_alignments"]),
        ("target_fluency", delivery["fluency_issues"]),
        ("expression_efficiency", delivery["efficiency_issues"]),
    )
    for dimension, rows in dimensions:
        for item in rows:
            if item.get("error_ref"):
                candidates.append({"error_ref": item["error_ref"], "dimension": dimension, "item": item})
    return candidates


def _review_errors(
    candidates: list[dict[str, Any]],
    card: dict[str, Any],
    target_analysis: dict[str, Any],
    translation: str,
    client: LLMClient | None,
    traces: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    expected = {item["error_ref"] for item in candidates}
    if not candidates or client is None:
        return {ref: _uncertain_review("No review model configured") for ref in expected}
    response = client.generate_json(
        load_prompt("error_review"),
        {
            "source_card": card,
            "target_translation": translation,
            "target_analysis": target_analysis,
            "candidate_errors": candidates,
        },
        task="review_candidate_errors",
    )
    traces.append(_trace("review_candidate_errors", response))
    raw = _unwrap(response.data, "review")
    decisions: dict[str, dict[str, Any]] = {}
    dimension_by_ref = {item["error_ref"]: item["dimension"] for item in candidates}
    for item in _records(raw.get("decisions")):
        ref = str(item.get("error_ref") or "")
        if ref not in expected:
            continue
        decision = str(item.get("decision") or "uncertain").strip().lower()
        if decision not in {"valid", "invalid", "uncertain"}:
            decision = "uncertain"
        spans = _valid_spans(item.get("counterevidence_spans"), translation)
        if decision == "invalid" and dimension_by_ref[ref] in {"anchor_accuracy", "event_preservation", "relation_preservation"} and not spans:
            decision = "uncertain"
        duplicate_of = str(item.get("duplicate_of") or "").strip() or None
        if duplicate_of not in expected or duplicate_of == ref:
            duplicate_of = None
        decisions[ref] = {
            "decision": decision,
            "resolved_verdict": str(item.get("resolved_verdict") or "").strip() or None,
            "counterevidence_spans": spans,
            "duplicate_of": duplicate_of,
            "confidence": _confidence(item.get("confidence")),
            "reason": str(item.get("reason") or "No review reason supplied"),
        }
    for ref in expected - decisions.keys():
        decisions[ref] = _uncertain_review("Review model omitted this error")
    return decisions


def _attach_reviews(alignment: dict[str, Any], delivery: dict[str, Any], decisions: dict[str, dict[str, Any]]) -> None:
    for key in ("anchor_alignments", "event_alignments", "relation_alignments"):
        for item in alignment[key]:
            ref = item.get("error_ref")
            if ref:
                item["review"] = decisions.get(ref, _uncertain_review("Missing review"))
    for key in ("fluency_issues", "efficiency_issues"):
        for item in delivery[key]:
            item["review"] = decisions.get(item["error_ref"], _uncertain_review("Missing review"))


def _ok_verdicts(id_key: str) -> set[str]:
    return {"anchor_id": ANCHOR_OK, "event_id": EVENT_OK, "relation_id": RELATION_OK}[id_key]


def _uncertain_review(reason: str) -> dict[str, Any]:
    return {"decision": "uncertain", "resolved_verdict": None, "counterevidence_spans": [], "duplicate_of": None, "confidence": 0.0, "reason": reason}


def _trace(task: str, response: LLMResponse) -> dict[str, Any]:
    return {"task": task, "provider": response.provider, "model": response.model, "request_id": response.request_id, "usage": response.usage}


def _unwrap(data: dict[str, Any], key: str) -> dict[str, Any]:
    nested = data.get(key)
    return nested if isinstance(nested, dict) else data


def _valid_spans(value: Any, text: str) -> list[str]:
    return [span for span in _strings(value) if span in text]


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _confidence(value: Any) -> float:
    try:
        return round(min(1.0, max(0.0, float(value))), 4)
    except (TypeError, ValueError):
        return 0.0
