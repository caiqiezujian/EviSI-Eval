from __future__ import annotations

from collections import Counter
import re
from typing import Any


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
ALIGNMENT_STATUSES = {"aligned", "source_omitted", "target_addition", "uncertain"}
SEVERITIES = {"minor", "moderate", "major", "critical"}


def validate_source_units(artifact: dict[str, Any], source_text: str) -> list[str]:
    issues: list[str] = []
    units = _records(artifact.get("source_units"))
    _sequential_ids(units, "source_unit_id", "S", "source_units", issues)
    if not units:
        issues.append("source_units must contain at least one unit")
    if "".join(str(row.get("source_unit") or "") for row in units) != source_text:
        issues.append("source_units must concatenate exactly to source_text")
    terminal_boundaries = len(re.findall(r"[.!?。！？](?=\s|$|[\"'”’)])", source_text))
    if terminal_boundaries >= 2 and len(units) == 1:
        issues.append("multi-sentence source_text must not be returned as one trivial source unit")
    for row in units:
        if not str(row.get("source_unit") or ""):
            issues.append(f"source unit {row.get('source_unit_id')} is empty")
    return issues


def validate_eval_units(
    artifact: dict[str, Any], source_units: list[dict[str, Any]], translation: str
) -> list[str]:
    issues: list[str] = []
    rows = _records(artifact.get("eval_units"))
    _sequential_ids(rows, "eval_unit_id", "E", "eval_units", issues)
    if not rows:
        issues.append("eval_units must contain at least one unit")
    if "".join(str(row.get("target_unit") or "") for row in rows) != translation:
        issues.append("non-empty target_unit values must concatenate exactly to si_translation")

    source_order = {str(row.get("source_unit_id")): index for index, row in enumerate(source_units)}
    occurrences: list[str] = []
    for row in rows:
        eval_id = row.get("eval_unit_id")
        source_ids = _strings(row.get("source_unit_ids"))
        target_unit = str(row.get("target_unit") or "")
        status = str(row.get("alignment_status") or "")
        unknown = [item for item in source_ids if item not in source_order]
        if unknown:
            issues.append(f"eval unit {eval_id} references unknown source units: {unknown}")
        indexes = [source_order[item] for item in source_ids if item in source_order]
        if indexes and indexes != list(range(min(indexes), max(indexes) + 1)):
            issues.append(f"eval unit {eval_id} source_unit_ids must be adjacent and ordered")
        occurrences.extend(source_ids)
        if status not in ALIGNMENT_STATUSES:
            issues.append(f"eval unit {eval_id} has unsupported alignment_status")
        elif status == "aligned" and (not source_ids or not target_unit):
            issues.append(f"aligned eval unit {eval_id} needs source_unit_ids and target_unit")
        elif status == "source_omitted" and (not source_ids or target_unit):
            issues.append(f"source_omitted eval unit {eval_id} needs source IDs and empty target_unit")
        elif status == "target_addition" and (source_ids or not target_unit):
            issues.append(f"target_addition eval unit {eval_id} needs empty source IDs and target text")
        elif status == "uncertain" and not source_ids and not target_unit:
            issues.append(f"uncertain eval unit {eval_id} cannot be empty on both sides")

    counts = Counter(occurrences)
    expected = set(source_order)
    if set(counts) != expected or any(count != 1 for count in counts.values()):
        issues.append("every source_unit_id must occur exactly once across eval_units")
    return issues


def validate_anchor_extraction(
    artifact: dict[str, Any], units: list[dict[str, Any]], source_side: bool
) -> list[str]:
    list_key = "source_anchors" if source_side else "target_anchors"
    unit_id_key = "source_unit_id" if source_side else "eval_unit_id"
    unit_text_key = "source_unit" if source_side else "target_unit"
    item_id_key = "source_anchor_id" if source_side else "target_anchor_id"
    prefix = "SA" if source_side else "TA"
    return _validate_semantic_items(
        artifact, list_key, units, unit_id_key, unit_text_key, item_id_key, prefix,
        required_fields=("anchor_text", "normalized_meaning", "evidence_span"),
    )


def validate_event_extraction(
    artifact: dict[str, Any], units: list[dict[str, Any]], source_side: bool
) -> list[str]:
    list_key = "source_events" if source_side else "target_events"
    unit_id_key = "source_unit_id" if source_side else "eval_unit_id"
    unit_text_key = "source_unit" if source_side else "target_unit"
    item_id_key = "source_event_id" if source_side else "target_event_id"
    prefix = "SE" if source_side else "TE"
    return _validate_semantic_items(
        artifact, list_key, units, unit_id_key, unit_text_key, item_id_key, prefix,
        required_fields=("event_text", "canonical_meaning", "evidence_span"),
    )


def validate_relation_extraction(
    artifact: dict[str, Any], units: list[dict[str, Any]], events: list[dict[str, Any]], source_side: bool
) -> list[str]:
    issues: list[str] = []
    list_key = "source_relations" if source_side else "target_relations"
    relation_id_key = "source_relation_id" if source_side else "target_relation_id"
    relation_prefix = "SR" if source_side else "TR"
    unit_ids_key = "source_unit_ids" if source_side else "eval_unit_ids"
    unit_id_key = "source_unit_id" if source_side else "eval_unit_id"
    unit_text_key = "source_unit" if source_side else "target_unit"
    event_id_key = "source_event_id" if source_side else "target_event_id"
    related_key = "related_source_event_ids" if source_side else "related_target_event_ids"
    rows = _records(artifact.get(list_key))
    _sequential_ids(rows, relation_id_key, relation_prefix, list_key, issues)
    unit_by_id = {str(row.get(unit_id_key)): str(row.get(unit_text_key) or "") for row in units}
    unit_order = {key: index for index, key in enumerate(unit_by_id)}
    event_ids = {str(row.get(event_id_key)) for row in events}
    for row in rows:
        relation_id = row.get(relation_id_key)
        selected_ids = _strings(row.get(unit_ids_key))
        if not selected_ids:
            issues.append(f"relation {relation_id} must reference at least one unit")
        if any(item not in unit_by_id for item in selected_ids):
            issues.append(f"relation {relation_id} references an unknown unit")
        indexes = [unit_order[item] for item in selected_ids if item in unit_order]
        if indexes and indexes != list(range(min(indexes), max(indexes) + 1)):
            issues.append(f"relation {relation_id} unit IDs must be adjacent and ordered")
        for key in ("relation_text", "relation_meaning"):
            if not str(row.get(key) or "").strip():
                issues.append(f"relation {relation_id} is missing {key}")
        evidence = _strings(row.get("evidence_spans"))
        if not evidence:
            issues.append(f"relation {relation_id} needs evidence_spans")
        selected_texts = [unit_by_id[item] for item in selected_ids if item in unit_by_id]
        for span in evidence:
            if not any(span in text for text in selected_texts):
                issues.append(f"relation {relation_id} has non-verbatim evidence")
        if any(item not in event_ids for item in _strings(row.get(related_key))):
            issues.append(f"relation {relation_id} references an unknown event")
    return issues


def validate_issue_evaluation(
    artifact: dict[str, Any], translation: str, issue_key: str, assessment_key: str, prefix: str
) -> list[str]:
    issues: list[str] = []
    rows = _records(artifact.get(issue_key))
    _sequential_ids(rows, "issue_id", prefix, issue_key, issues)
    if not str(artifact.get(assessment_key) or "").strip():
        issues.append(f"{assessment_key} is required")
    for row in rows:
        issue_id = row.get("issue_id")
        span = str(row.get("target_span") or "")
        if not span or span not in translation:
            issues.append(f"issue {issue_id} has non-verbatim target_span")
        if not str(row.get("issue_description") or "").strip():
            issues.append(f"issue {issue_id} is missing issue_description")
        if row.get("severity") not in SEVERITIES:
            issues.append(f"issue {issue_id} has unsupported severity")
    return issues


def validate_judgements(
    artifact: dict[str, Any], source_items: list[dict[str, Any]], target_items: list[dict[str, Any]],
    eval_units: list[dict[str, Any]], kind: str,
) -> list[str]:
    issues: list[str] = []
    config = {
        "anchor": ("anchor_judgements", "anchor_judgement_id", "AJ", "source_anchor_id", "target_anchor_ids", "target_anchor_id", {"correct", "partially_correct", "incorrect", "missing", "uncertain"}, "anchor_fidelity_assessment"),
        "event": ("event_judgements", "event_judgement_id", "EJ", "source_event_id", "target_event_ids", "target_event_id", {"correct", "partially_correct", "incorrect", "missing", "uncertain"}, "event_fidelity_assessment"),
        "relation": ("relation_judgements", "relation_judgement_id", "RJ", "source_relation_id", "target_relation_ids", "target_relation_id", {"correct", "weakened", "incorrect", "missing", "uncertain"}, "relation_fidelity_assessment"),
    }[kind]
    list_key, judgement_id_key, prefix, source_id_key, target_ids_key, target_id_key, verdicts, assessment_key = config
    rows = _records(artifact.get(list_key))
    _sequential_ids(rows, judgement_id_key, prefix, list_key, issues)
    expected = [str(item.get(source_id_key)) for item in source_items]
    actual = [str(item.get(source_id_key) or "") for item in rows]
    if actual != expected:
        issues.append(f"{list_key} must cover every {source_id_key} once in source order")
    target_ids = {str(item.get(target_id_key)) for item in target_items}
    eval_ids = {str(item.get("eval_unit_id")) for item in eval_units}
    target_text = "".join(str(item.get("target_unit") or "") for item in eval_units)
    for row in rows:
        judgement_id = row.get(judgement_id_key)
        source_item = next(
            (item for item in source_items if str(item.get(source_id_key)) == str(row.get(source_id_key))),
            None,
        )
        expected_source_field = {
            "anchor": ("source_anchor", "anchor_text"),
            "event": ("source_event", "event_text"),
            "relation": ("source_relation", "relation_text"),
        }[kind]
        if source_item is None or row.get(expected_source_field[0]) != source_item.get(expected_source_field[1]):
            issues.append(f"judgement {judgement_id} changed the frozen source item text")
        if kind != "relation" and row.get("eval_unit_id") not in eval_ids:
            issues.append(f"judgement {judgement_id} references unknown eval_unit_id")
        if any(item not in target_ids for item in _strings(row.get(target_ids_key))):
            issues.append(f"judgement {judgement_id} references unknown target item")
        target_match = str(row.get("target_match") or "")
        if target_match and target_match not in target_text:
            issues.append(f"judgement {judgement_id} has non-verbatim target_match")
        if row.get("verdict") not in verdicts:
            issues.append(f"judgement {judgement_id} has unsupported verdict")
        verdict = row.get("verdict")
        positive_or_error = verdict not in {"missing", "uncertain"}
        if positive_or_error and (not _strings(row.get(target_ids_key)) or not target_match):
            issues.append(f"judgement {judgement_id} needs target IDs and verbatim target_match for verdict {verdict}")
        if verdict == "missing" and (_strings(row.get(target_ids_key)) or target_match):
            issues.append(f"missing judgement {judgement_id} must not cite target evidence")
        if not str(row.get("explanation") or "").strip():
            issues.append(f"judgement {judgement_id} is missing explanation")
    if not str(artifact.get(assessment_key) or "").strip():
        issues.append(f"{assessment_key} is required")
    return issues


def validate_global_review(artifact: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    review = artifact.get("global_fidelity_review")
    if not isinstance(review, dict):
        return ["global_fidelity_review must be an object"]
    for key in (
        "delayed_expression_notes", "consistency_notes", "possible_duplicate_errors",
        "missed_global_issues", "misleading_addition_notes",
    ):
        if not isinstance(review.get(key), list) or any(not isinstance(item, str) for item in review.get(key, [])):
            issues.append(f"global_fidelity_review.{key} must be an array of strings")
    if not str(review.get("overall_fidelity_comment") or "").strip():
        issues.append("global_fidelity_review.overall_fidelity_comment is required")
    return issues


def validate_dimension_scores(artifact: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    scores = artifact.get("dimension_scores")
    explanations = artifact.get("dimension_score_explanations")
    if not isinstance(scores, dict):
        return ["dimension_scores must be an object"]
    if not isinstance(explanations, dict):
        return ["dimension_score_explanations must be an object"]
    if set(scores) != set(DIMENSIONS):
        issues.append("dimension_scores must contain exactly the five protocol dimensions")
    if set(explanations) != set(DIMENSIONS):
        issues.append("dimension_score_explanations must contain exactly the five protocol dimensions")
    for dimension in DIMENSIONS:
        value = scores.get(dimension)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 100:
            issues.append(f"dimension score {dimension} must be between 0 and 100")
        if not str(explanations.get(dimension) or "").strip():
            issues.append(f"dimension explanation {dimension} is required")
    return issues


def validate_final_summary(artifact: dict[str, Any], expected_score: float) -> list[str]:
    issues: list[str] = []
    if artifact.get("dimension_weights") != DIMENSION_WEIGHTS:
        issues.append("dimension_weights must match the fixed protocol weights")
    score = artifact.get("final_score")
    if not isinstance(score, (int, float)) or abs(float(score) - expected_score) > 0.01:
        issues.append("final_score must equal the program-computed score")
    summary = artifact.get("score_summary")
    if not isinstance(summary, dict):
        return issues + ["score_summary must be an object"]
    if not str(summary.get("overall_judgement") or "").strip():
        issues.append("score_summary.overall_judgement is required")
    for key in ("main_strengths", "main_errors", "uncertain_points"):
        if not isinstance(summary.get(key), list) or any(not isinstance(item, str) for item in summary.get(key, [])):
            issues.append(f"score_summary.{key} must be an array of strings")
    return issues


def weighted_score(scores: dict[str, Any]) -> float:
    return round(sum(float(scores[key]) * DIMENSION_WEIGHTS[key] / 100 for key in DIMENSIONS), 2)


def _validate_semantic_items(
    artifact: dict[str, Any], list_key: str, units: list[dict[str, Any]], unit_id_key: str,
    unit_text_key: str, item_id_key: str, prefix: str, required_fields: tuple[str, ...],
) -> list[str]:
    issues: list[str] = []
    rows = _records(artifact.get(list_key))
    _sequential_ids(rows, item_id_key, prefix, list_key, issues)
    unit_by_id = {str(row.get(unit_id_key)): str(row.get(unit_text_key) or "") for row in units}
    for row in rows:
        item_id = row.get(item_id_key)
        unit_id = str(row.get(unit_id_key) or "")
        if unit_id not in unit_by_id:
            issues.append(f"item {item_id} references unknown {unit_id_key}")
        for key in required_fields:
            if not str(row.get(key) or "").strip():
                issues.append(f"item {item_id} is missing {key}")
        evidence = str(row.get("evidence_span") or "")
        if not evidence or evidence not in unit_by_id.get(unit_id, ""):
            issues.append(f"item {item_id} has non-verbatim evidence_span")
    return issues


def _sequential_ids(
    rows: list[dict[str, Any]], key: str, prefix: str, label: str, issues: list[str]
) -> None:
    actual = [str(row.get(key) or "") for row in rows]
    expected = [f"{prefix}{index}" for index in range(1, len(rows) + 1)]
    if actual != expected:
        issues.append(f"{label}.{key} values must be unique and sequential: {expected}")


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value if isinstance(item, str) and item] if isinstance(value, list) else []
