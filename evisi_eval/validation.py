from __future__ import annotations

import re
from collections import Counter
from typing import Any


PROTOCOL_VERSION = "evisi_eval_v0.5"
DIMENSIONS = (
    "anchor_fidelity",
    "event_fidelity",
    "relation_fidelity",
    "fluency",
    "si_expression",
)
DIMENSION_WEIGHTS = {
    "anchor_fidelity": 30,
    "event_fidelity": 25,
    "relation_fidelity": 20,
    "fluency": 15,
    "si_expression": 10,
}
VERDICT_VALUES = {
    "correct": 1.0,
    "partially_correct": 0.5,
    "weakened": 0.5,
    "incorrect": 0.0,
    "missing": 0.0,
}
SEVERITY_DEDUCTIONS = {"minor": 2.0, "moderate": 6.0, "major": 15.0, "critical": 35.0}
ALIGNMENT_STATUSES = {"aligned", "source_omitted", "target_addition", "uncertain"}
SEVERITIES = set(SEVERITY_DEDUCTIONS)
MIN_FINAL_CONFIDENCE = 0.60
ANCHOR_TYPES = {"A-ENT", "A-QNT", "A-TMP", "A-TERM", "A-SCOPE"}
EVENT_TYPES = {"E-ACT", "E-STATE", "E-CHANGE", "E-JUDG", "E-REL", "E-SPEECH", "E-MODAL"}
RELATION_TYPES = {
    "cause_effect", "condition_consequence", "purpose", "concession", "contrast",
    "temporal_sequence", "temporal_overlap", "conjunction", "progression", "similarity",
    "difference", "degree", "elaboration", "attribution", "exemplification", "exception",
    "conclusion",
}
RELATION_BASES = {"explicit_cue", "strong_semantic_entailment"}


def validate_source_card_artifact(artifact: dict[str, Any], source_text: str) -> list[str]:
    issues = _require_array_fields(
        artifact, ("source_units", "source_anchors", "source_events", "source_relations")
    )
    issues.extend(validate_source_units(artifact, source_text))
    units = _records(artifact.get("source_units"))
    issues.extend(_validate_items(artifact, "source_anchors", units, True, "anchor"))
    issues.extend(_validate_items(artifact, "source_events", units, True, "event"))
    issues.extend(_validate_relations(artifact, units, _records(artifact.get("source_events")), True))
    return issues


def validate_source_units(artifact: dict[str, Any], source_text: str) -> list[str]:
    issues: list[str] = []
    units = _records(artifact.get("source_units"))
    _sequential_ids(units, "source_unit_id", "S", "source_units", issues)
    if not units:
        issues.append("source_units must contain at least one unit")
    if "".join(str(row.get("source_unit") or "") for row in units) != source_text:
        issues.append("source_units must concatenate exactly to source_text")
    boundaries = len(re.findall(r"[.!?。！？](?=\s|$|[\"'”’)])", source_text))
    if boundaries >= 2 and len(units) == 1:
        issues.append("multi-sentence source_text must not collapse to one source unit")
    if any(not str(row.get("source_unit") or "") for row in units):
        issues.append("source_units cannot contain empty text")
    return issues


def validate_alignment_artifact(
    artifact: dict[str, Any], source_units: list[dict[str, Any]], translation: str
) -> list[str]:
    issues = _require_array_fields(artifact, ("eval_units",))
    rows = _records(artifact.get("eval_units"))
    _sequential_ids(rows, "eval_unit_id", "E", "eval_units", issues)
    if not rows:
        issues.append("eval_units must contain at least one unit")
    if "".join(str(row.get("target_unit") or "") for row in rows) != translation:
        issues.append("target_unit values must concatenate exactly to si_translation")
    source_order = {str(row.get("source_unit_id")): index for index, row in enumerate(source_units)}
    occurrences: list[str] = []
    for row in rows:
        eval_id = str(row.get("eval_unit_id") or "")
        source_ids = _strings(row.get("source_unit_ids"))
        target_text = str(row.get("target_unit") or "")
        status = str(row.get("alignment_status") or "")
        indexes = [source_order[item] for item in source_ids if item in source_order]
        if len(indexes) != len(source_ids):
            issues.append(f"eval unit {eval_id} references unknown source_unit_id")
        if indexes and indexes != list(range(min(indexes), max(indexes) + 1)):
            issues.append(f"eval unit {eval_id} source_unit_ids must be adjacent and ordered")
        occurrences.extend(source_ids)
        if status not in ALIGNMENT_STATUSES:
            issues.append(f"eval unit {eval_id} has unsupported alignment_status")
        elif status == "aligned" and (not source_ids or not target_text):
            issues.append(f"aligned eval unit {eval_id} needs both source and target")
        elif status == "source_omitted" and (not source_ids or target_text):
            issues.append(f"source_omitted eval unit {eval_id} needs source IDs and empty target")
        elif status == "target_addition" and (source_ids or not target_text):
            issues.append(f"target_addition eval unit {eval_id} needs target text and no source IDs")
        elif status == "uncertain" and not source_ids and not target_text:
            issues.append(f"uncertain eval unit {eval_id} cannot be empty on both sides")
        if not str(row.get("reason") or "").strip():
            issues.append(f"eval unit {eval_id} needs a reason")
    counts = Counter(occurrences)
    if set(counts) != set(source_order) or any(value != 1 for value in counts.values()):
        issues.append("every source_unit_id must occur exactly once across eval_units")
    return issues


def validate_target_evidence_artifact(
    artifact: dict[str, Any], target_units: list[dict[str, Any]]
) -> list[str]:
    issues = _require_array_fields(
        artifact, ("target_anchors", "target_events", "target_relations")
    )
    issues.extend(_validate_items(artifact, "target_anchors", target_units, False, "anchor"))
    issues.extend(_validate_items(artifact, "target_events", target_units, False, "event"))
    issues.extend(_validate_relations(artifact, target_units, _records(artifact.get("target_events")), False))
    return issues


def validate_delivery_artifact(
    artifact: dict[str, Any], translation: str, issue_key: str, assessment_key: str, prefix: str
) -> list[str]:
    issues = _require_array_fields(artifact, (issue_key,))
    rows = _records(artifact.get(issue_key))
    _sequential_ids(rows, "issue_id", prefix, issue_key, issues)
    if not str(artifact.get(assessment_key) or "").strip():
        issues.append(f"{assessment_key} is required")
    seen_spans: set[str] = set()
    for row in rows:
        issue_id = str(row.get("issue_id") or "")
        span = str(row.get("target_span") or "")
        if not span or span not in translation:
            issues.append(f"issue {issue_id} has non-verbatim target_span")
        if not str(row.get("issue_type") or "").strip():
            issues.append(f"issue {issue_id} is missing issue_type")
        if not str(row.get("reason") or "").strip():
            issues.append(f"issue {issue_id} is missing reason")
        if row.get("severity") not in SEVERITIES:
            issues.append(f"issue {issue_id} has unsupported severity")
        if span in seen_spans:
            issues.append(f"issue {issue_id} duplicates an already penalized target_span")
        seen_spans.add(span)
    return issues


def validate_judgement_artifact(
    artifact: dict[str, Any], source_card: dict[str, Any], target_card: dict[str, Any]
) -> list[str]:
    issues = _require_array_fields(
        artifact, ("anchor_judgements", "event_judgements", "relation_judgements")
    )
    for kind in ("anchor", "event", "relation"):
        issues.extend(_validate_judgement_kind(artifact, source_card, target_card, kind))
    return issues


def validate_adjudication_artifact(
    artifact: dict[str, Any], disagreement_ids: set[str], source_card: dict[str, Any],
    target_card: dict[str, Any],
) -> list[str]:
    rows = _records(artifact.get("adjudications"))
    issues = _require_array_fields(artifact, ("adjudications",))
    actual = [str(row.get("judgement_id") or "") for row in rows]
    if set(actual) != disagreement_ids or len(actual) != len(set(actual)):
        issues.append("adjudications must cover every disagreement exactly once")
    synthetic = {
        "anchor_judgements": [], "event_judgements": [], "relation_judgements": []
    }
    for row in rows:
        judgement_id = str(row.get("judgement_id") or "")
        kind = _kind_from_judgement_id(judgement_id)
        if kind is None:
            issues.append(f"adjudication has invalid judgement_id={judgement_id}")
            continue
        synthetic[f"{kind}_judgements"].append(row)
    for kind in ("anchor", "event", "relation"):
        expected = {item for item in disagreement_ids if _kind_from_judgement_id(item) == kind}
        issues.extend(
            _validate_judgement_kind(
                synthetic, source_card, target_card, kind, expected_judgement_ids=expected
            )
        )
    return issues


def calculate_scores(
    final_judgements: dict[str, list[dict[str, Any]]], fluency_issues: list[dict[str, Any]],
    expression_issues: list[dict[str, Any]], source_card: dict[str, Any],
) -> dict[str, Any]:
    scores: dict[str, float | None] = {}
    diagnostics: dict[str, Any] = {}
    for kind, dimension, source_key, source_id_key in (
        ("anchor", "anchor_fidelity", "source_anchors", "source_anchor_id"),
        ("event", "event_fidelity", "source_events", "source_event_id"),
        ("relation", "relation_fidelity", "source_relations", "source_relation_id"),
    ):
        source_by_id = {str(item[source_id_key]): item for item in _records(source_card.get(source_key))}
        rows = final_judgements.get(f"{kind}_judgements", [])
        total_weight = sum(int(item.get("importance", 1)) for item in source_by_id.values())
        decided_weight = 0
        earned = 0.0
        uncertain_weight = 0
        low_confidence = 0
        counts = Counter()
        for row in rows:
            verdict = str(row.get("verdict") or "uncertain")
            counts[verdict] += 1
            source_id = str(row.get(source_id_key) or "")
            weight = int(source_by_id.get(source_id, {}).get("importance", 1))
            if float(row.get("confidence", 0)) < MIN_FINAL_CONFIDENCE:
                low_confidence += 1
            if verdict == "uncertain":
                uncertain_weight += weight
                continue
            decided_weight += weight
            earned += weight * VERDICT_VALUES.get(verdict, 0.0)
        if total_weight == 0:
            score = 100.0
            coverage = 100.0
            applicable = False
            decision_status = "not_applicable"
        elif decided_weight == 0:
            score = None
            coverage = 0.0
            applicable = True
            decision_status = "no_decisions"
        else:
            score = round(100 * earned / decided_weight, 2)
            coverage = round(100 * decided_weight / total_weight, 2)
            applicable = True
            decision_status = "complete" if decided_weight == total_weight else "partial_decisions"
        scores[dimension] = score
        diagnostics[dimension] = {
            "applicable": applicable,
            "decision_status": decision_status,
            "item_count": len(rows),
            "verdict_counts": dict(counts),
            "total_importance_weight": total_weight,
            "decided_importance_weight": decided_weight,
            "uncertain_importance_weight": uncertain_weight,
            "coverage": coverage,
            "low_confidence_count": low_confidence,
        }

    for dimension, issues in (("fluency", fluency_issues), ("si_expression", expression_issues)):
        deductions = [SEVERITY_DEDUCTIONS.get(str(item.get("severity")), 0.0) for item in issues]
        scores[dimension] = round(max(0.0, 100.0 - sum(deductions)), 2)
        diagnostics[dimension] = {
            "issue_count": len(issues),
            "severity_counts": dict(Counter(str(item.get("severity")) for item in issues)),
            "deductions": deductions,
            "total_deduction": round(sum(deductions), 2),
        }

    no_decisions = any(
        diagnostics[key].get("decision_status") == "no_decisions"
        for key in ("anchor_fidelity", "event_fidelity", "relation_fidelity")
    )
    provisional = any(
        diagnostics[key].get("uncertain_importance_weight", 0) > 0
        or diagnostics[key].get("low_confidence_count", 0) > 0
        for key in ("anchor_fidelity", "event_fidelity", "relation_fidelity")
    )
    active_dimensions = [
        key for key in DIMENSIONS
        if key in {"fluency", "si_expression"} or diagnostics[key].get("applicable", False)
    ]
    active_weight = sum(DIMENSION_WEIGHTS[key] for key in active_dimensions)
    final_score = None
    if not no_decisions:
        final_score = round(
            sum(float(scores[key]) * DIMENSION_WEIGHTS[key] for key in active_dimensions)
            / active_weight,
            2,
        )
    effective_weights = {
        key: round(100 * DIMENSION_WEIGHTS[key] / active_weight, 4) if key in active_dimensions else 0.0
        for key in DIMENSIONS
    }
    return {
        "dimension_scores": scores,
        "dimension_weights": dict(DIMENSION_WEIGHTS),
        "effective_dimension_weights": effective_weights,
        "score_diagnostics": diagnostics,
        "final_score": final_score,
        "score_status": (
            "provisional_no_decisions"
            if no_decisions
            else "provisional_review_required"
            if provisional
            else "final"
        ),
    }


def validate_summary_artifact(artifact: dict[str, Any]) -> list[str]:
    summary = artifact.get("score_summary")
    if not isinstance(summary, dict):
        return ["score_summary must be an object"]
    issues: list[str] = []
    if not str(summary.get("overall_judgement") or "").strip():
        issues.append("score_summary.overall_judgement is required")
    for key in ("main_strengths", "main_errors", "uncertain_points"):
        if not isinstance(summary.get(key), list) or any(
            not isinstance(item, str) for item in summary.get(key, [])
        ):
            issues.append(f"score_summary.{key} must be an array of strings")
    return issues


def _validate_items(
    artifact: dict[str, Any], list_key: str, units: list[dict[str, Any]], source_side: bool,
    kind: str,
) -> list[str]:
    issues: list[str] = []
    unit_id_key = "source_unit_id" if source_side else "eval_unit_id"
    unit_text_key = "source_unit" if source_side else "target_unit"
    item_id_key = f"{'source' if source_side else 'target'}_{kind}_id"
    prefix = {("anchor", True): "SA", ("event", True): "SE", ("anchor", False): "TA", ("event", False): "TE"}[(kind, source_side)]
    rows = _records(artifact.get(list_key))
    _sequential_ids(rows, item_id_key, prefix, list_key, issues)
    unit_by_id = {str(row.get(unit_id_key)): str(row.get(unit_text_key) or "") for row in units}
    required = ("anchor_text", "normalized_meaning") if kind == "anchor" else ("event_text", "canonical_meaning")
    for row in rows:
        item_id = str(row.get(item_id_key) or "")
        unit_id = str(row.get(unit_id_key) or "")
        if unit_id not in unit_by_id:
            issues.append(f"item {item_id} references unknown {unit_id_key}")
        if any(not str(row.get(key) or "").strip() for key in required):
            issues.append(f"item {item_id} is missing semantic fields")
        type_key = "anchor_type" if kind == "anchor" else "event_type"
        allowed_types = ANCHOR_TYPES if kind == "anchor" else EVENT_TYPES
        if row.get(type_key) not in allowed_types:
            issues.append(f"item {item_id} has unsupported {type_key}")
        evidence = str(row.get("evidence_span") or "")
        if not evidence or evidence not in unit_by_id.get(unit_id, ""):
            issues.append(f"item {item_id} has non-verbatim evidence_span")
        if source_side and row.get("importance") not in {1, 2, 3}:
            issues.append(f"item {item_id} importance must be 1, 2, or 3")
    return issues


def _validate_relations(
    artifact: dict[str, Any], units: list[dict[str, Any]], events: list[dict[str, Any]],
    source_side: bool,
) -> list[str]:
    issues: list[str] = []
    side = "source" if source_side else "target"
    list_key = f"{side}_relations"
    relation_id_key = f"{side}_relation_id"
    unit_ids_key = "source_unit_ids" if source_side else "eval_unit_ids"
    unit_id_key = "source_unit_id" if source_side else "eval_unit_id"
    unit_text_key = "source_unit" if source_side else "target_unit"
    event_id_key = f"{side}_event_id"
    event_unit_key = "source_unit_id" if source_side else "eval_unit_id"
    related_key = f"related_{side}_event_ids"
    rows = _records(artifact.get(list_key))
    _sequential_ids(rows, relation_id_key, "SR" if source_side else "TR", list_key, issues)
    unit_by_id = {str(row.get(unit_id_key)): str(row.get(unit_text_key) or "") for row in units}
    unit_order = {key: index for index, key in enumerate(unit_by_id)}
    event_by_id = {str(row.get(event_id_key)): row for row in events}
    event_ids = set(event_by_id)
    for row in rows:
        relation_id = str(row.get(relation_id_key) or "")
        selected = _strings(row.get(unit_ids_key))
        indexes = [unit_order[item] for item in selected if item in unit_order]
        if not selected or len(indexes) != len(selected):
            issues.append(f"relation {relation_id} references invalid units")
        elif len(indexes) != len(set(indexes)) or indexes != sorted(indexes):
            issues.append(f"relation {relation_id} units must be unique and ordered")
        if not str(row.get("relation_text") or "").strip() or not str(row.get("relation_meaning") or "").strip():
            issues.append(f"relation {relation_id} is missing semantic fields")
        if row.get("relation_type") not in RELATION_TYPES:
            issues.append(f"relation {relation_id} has unsupported relation_type")
        basis = str(row.get("relation_basis") or "")
        if basis not in RELATION_BASES:
            issues.append(f"relation {relation_id} has unsupported relation_basis")
        cue = str(row.get("relation_cue") or "")
        confidence = row.get("confidence")
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0 <= confidence <= 1
        ):
            issues.append(f"relation {relation_id} confidence must be between 0 and 1")
        elif basis == "strong_semantic_entailment" and confidence < 0.85:
            issues.append(f"implicit relation {relation_id} confidence must be at least 0.85")
        evidence = _strings(row.get("evidence_spans"))
        selected_texts = [unit_by_id[item] for item in selected if item in unit_by_id]
        if not evidence or any(not any(span in text for text in selected_texts) for span in evidence):
            issues.append(f"relation {relation_id} has invalid evidence_spans")
        if basis == "explicit_cue" and (not cue or not any(cue in text for text in selected_texts)):
            issues.append(f"explicit relation {relation_id} needs a verbatim relation_cue")
        if basis == "strong_semantic_entailment" and cue:
            issues.append(f"implicit relation {relation_id} must use an empty relation_cue")
        related_events = _strings(row.get(related_key))
        if len(related_events) < 2 or len(related_events) != len(set(related_events)):
            issues.append(f"relation {relation_id} must link at least two distinct events")
        if any(item not in event_ids for item in related_events):
            issues.append(f"relation {relation_id} references unknown event")
        selected_set = set(selected)
        for event_id in related_events:
            event = event_by_id.get(event_id)
            if event is not None and str(event.get(event_unit_key) or "") not in selected_set:
                issues.append(f"relation {relation_id} links an event outside its selected units")
        if source_side and row.get("importance") not in {1, 2, 3}:
            issues.append(f"relation {relation_id} importance must be 1, 2, or 3")
    return issues


def _validate_judgement_kind(
    artifact: dict[str, Any], source_card: dict[str, Any], target_card: dict[str, Any],
    kind: str, expected_judgement_ids: set[str] | None = None,
) -> list[str]:
    issues: list[str] = []
    config = {
        "anchor": ("anchor_judgements", "AJ", "source_anchors", "source_anchor_id", "target_anchors", "target_anchor_id", {"correct", "partially_correct", "incorrect", "missing", "uncertain"}),
        "event": ("event_judgements", "EJ", "source_events", "source_event_id", "target_events", "target_event_id", {"correct", "partially_correct", "incorrect", "missing", "uncertain"}),
        "relation": ("relation_judgements", "RJ", "source_relations", "source_relation_id", "target_relations", "target_relation_id", {"correct", "weakened", "incorrect", "missing", "uncertain"}),
    }[kind]
    list_key, prefix, source_key, source_id_key, target_key, target_id_key, verdicts = config
    rows = _records(artifact.get(list_key))
    source_items = _records(source_card.get(source_key))
    source_by_id = {str(item.get(source_id_key)): item for item in source_items}
    if expected_judgement_ids is None:
        expected_source_ids = list(source_by_id)
        expected_judgement_ids = {f"{prefix}{index}" for index in range(1, len(expected_source_ids) + 1)}
        actual_source_ids = [str(row.get(source_id_key) or "") for row in rows]
        if actual_source_ids != expected_source_ids:
            issues.append(f"{list_key} must cover source items once in source order")
    actual_judgement_ids = [str(row.get("judgement_id") or "") for row in rows]
    if set(actual_judgement_ids) != expected_judgement_ids or len(actual_judgement_ids) != len(set(actual_judgement_ids)):
        issues.append(f"{list_key} judgement IDs do not match expected set")

    target_items = _records(target_card.get(target_key))
    target_by_id = {str(item.get(target_id_key)): item for item in target_items}
    eval_units = _records(target_card.get("eval_units"))
    eval_by_id = {str(item.get("eval_unit_id")): item for item in eval_units}
    for row in rows:
        judgement_id = str(row.get("judgement_id") or "")
        source_id = str(row.get(source_id_key) or "")
        source = source_by_id.get(source_id)
        if source is None:
            issues.append(f"judgement {judgement_id} references unknown source item")
            continue
        expected_index = list(source_by_id).index(source_id) + 1
        if judgement_id != f"{prefix}{expected_index}":
            issues.append(
                f"judgement {judgement_id} must map to {source_id} as {prefix}{expected_index}"
            )
        expected_source_evidence = _item_evidence(source)
        if _strings(row.get("source_evidence_spans")) != expected_source_evidence:
            issues.append(f"judgement {judgement_id} changed source evidence")
        eval_ids = _strings(row.get("eval_unit_ids"))
        allowed_eval_ids = _allowed_eval_ids(source, kind, eval_units)
        if not eval_ids or any(item not in allowed_eval_ids for item in eval_ids):
            issues.append(f"judgement {judgement_id} cites non-local eval units")
        target_ids = _strings(row.get(f"target_{kind}_ids"))
        if any(item not in target_by_id for item in target_ids):
            issues.append(f"judgement {judgement_id} references unknown target item")
        for target_id in target_ids:
            if target_id not in target_by_id:
                continue
            target_eval_ids = _item_unit_ids(target_by_id[target_id], kind)
            if any(item not in eval_ids for item in target_eval_ids):
                issues.append(f"judgement {judgement_id} target item is outside cited eval units")
        target_evidence = _strings(row.get("target_evidence_spans"))
        allowed_evidence = [
            span for item in target_ids if item in target_by_id
            for span in _item_evidence(target_by_id[item])
        ]
        if any(span not in allowed_evidence for span in target_evidence):
            issues.append(f"judgement {judgement_id} target evidence is not from cited target items")
        verdict = str(row.get("verdict") or "")
        if verdict not in verdicts:
            issues.append(f"judgement {judgement_id} has unsupported verdict")
        if verdict in {"correct", "partially_correct", "weakened", "incorrect"} and (not target_ids or not target_evidence):
            issues.append(f"judgement {judgement_id} needs cited target evidence")
        if verdict == "missing" and (target_ids or target_evidence):
            issues.append(f"missing judgement {judgement_id} cannot cite target evidence")
        confidence = row.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            issues.append(f"judgement {judgement_id} confidence must be between 0 and 1")
        if not str(row.get("reason") or "").strip():
            issues.append(f"judgement {judgement_id} is missing reason")
    return issues


def _allowed_eval_ids(source: dict[str, Any], kind: str, eval_units: list[dict[str, Any]]) -> set[str]:
    source_unit_ids = _strings(source.get("source_unit_ids")) if kind == "relation" else [str(source.get("source_unit_id") or "")]
    direct_indexes = [
        index for index, unit in enumerate(eval_units)
        if set(source_unit_ids) & set(_strings(unit.get("source_unit_ids")))
    ]
    allowed_indexes = set(direct_indexes)
    for index in direct_indexes:
        allowed_indexes.update({index - 1, index + 1})
    return {
        str(eval_units[index].get("eval_unit_id"))
        for index in allowed_indexes if 0 <= index < len(eval_units)
    }


def _item_evidence(item: dict[str, Any]) -> list[str]:
    if isinstance(item.get("evidence_spans"), list):
        return _strings(item.get("evidence_spans"))
    span = str(item.get("evidence_span") or "")
    return [span] if span else []


def _item_unit_ids(item: dict[str, Any], kind: str) -> list[str]:
    if kind == "relation":
        return _strings(item.get("eval_unit_ids"))
    unit_id = str(item.get("eval_unit_id") or "")
    return [unit_id] if unit_id else []


def _kind_from_judgement_id(value: str) -> str | None:
    if value.startswith("AJ"):
        return "anchor"
    if value.startswith("EJ"):
        return "event"
    if value.startswith("RJ"):
        return "relation"
    return None


def _sequential_ids(rows: list[dict[str, Any]], key: str, prefix: str, label: str, issues: list[str]) -> None:
    actual = [str(row.get(key) or "") for row in rows]
    expected = [f"{prefix}{index}" for index in range(1, len(rows) + 1)]
    if actual != expected:
        issues.append(f"{label}.{key} values must be sequential: {expected}")


def _require_array_fields(artifact: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    return [f"{key} must be an array" for key in keys if not isinstance(artifact.get(key), list)]


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value if isinstance(item, str) and item] if isinstance(value, list) else []
