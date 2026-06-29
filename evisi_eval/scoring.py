from __future__ import annotations

import copy
from typing import Any


DIMENSION_WEIGHTS = {
    "anchor_accuracy": 30.0,
    "event_preservation": 40.0,
    "relation_preservation": 10.0,
    "target_fluency": 12.0,
    "expression_efficiency": 8.0,
}

STATUS_COEFFICIENTS = {
    "anchor_accuracy": {"exact": 0.0, "equivalent": 0.0, "incorrect": 1.0, "missing": 1.0, "ambiguous": 0.0},
    "event_preservation": {"covered": 0.0, "compressed_covered": 0.0, "partially_covered": 0.5, "contradicted": 1.0, "missing": 1.0, "ambiguous": 0.0},
    "relation_preservation": {"preserved": 0.0, "weakened": 0.5, "reversed": 1.0, "missing": 1.0, "ambiguous": 0.0},
}

DELIVERY_DEDUCTIONS = {
    "target_fluency": {"minor": 1.0, "major": 3.0, "critical": 6.0},
    "expression_efficiency": {"minor": 0.75, "major": 2.0, "critical": 4.0},
}

MIN_REVIEW_CONFIDENCE = 0.70


def score_evaluation(evaluation: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(evaluation)
    _suppress_relations_dependent_on_event_errors(result)
    dimensions: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    review_queue: list[dict[str, Any]] = []

    semantic_specs = (
        ("anchor_accuracy", "anchor_alignments", "anchor_id"),
        ("event_preservation", "event_alignments", "event_id"),
        ("relation_preservation", "relation_alignments", "relation_id"),
    )
    for dimension, result_key, id_key in semantic_specs:
        rows, summary, found, pending = _score_semantic_items(
            dimension, result.get(result_key, []), id_key
        )
        result[result_key] = rows
        dimensions[dimension] = summary
        errors.extend(found)
        review_queue.extend(pending)

    for dimension, result_key in (
        ("target_fluency", "fluency_issues"),
        ("expression_efficiency", "efficiency_issues"),
    ):
        rows, summary, found, pending = _score_delivery_items(
            dimension, result.get(result_key, [])
        )
        result[result_key] = rows
        dimensions[dimension] = summary
        errors.extend(found)
        review_queue.extend(pending)

    applicable = [item for item in dimensions.values() if item["applicable"]]
    evaluated_weight = sum(float(item["max_points"]) for item in applicable)
    earned = sum(float(item["score"]) for item in applicable)
    score_before_caps = 100.0 * earned / evaluated_weight if evaluated_weight else 0.0
    caps = _caps(errors)
    confirmed_caps = [item for item in caps if item["confirmed"]]
    score_cap = min((float(item["limit"]) for item in confirmed_caps), default=None)
    final_score = min(score_before_caps, score_cap) if score_cap is not None else score_before_caps

    result.update(
        {
            "scoring_protocol": "evisi_eval_v0.4.1",
            "dimension_weights": DIMENSION_WEIGHTS,
            "dimension_scores": dimensions,
            "evaluated_weight": round(evaluated_weight, 2),
            "score_before_caps": round(score_before_caps, 2),
            "final_score": round(final_score, 2),
            "score_cap": score_cap,
            "cap_reasons": confirmed_caps,
            "attributed_errors": errors,
            "review_queue": _dedupe(review_queue, "error_ref"),
        }
    )
    result.setdefault("metadata", {})
    result["metadata"].update(
        {
            "aggregation_is_deterministic": True,
            "model_generated_final_score": False,
            "error_count": len(errors),
            "review_required_count": len(result["review_queue"]),
        }
    )
    return result


def _suppress_relations_dependent_on_event_errors(result: dict[str, Any]) -> None:
    failed_events = {
        str(item.get("event_id"))
        for item in result.get("event_alignments", [])
        if str(item.get("verdict") or "") not in {"covered", "compressed_covered"}
        and item.get("error_scope") != "anchor_only"
    }
    for relation in result.get("relation_alignments", []):
        if relation.get("head_event_id") in failed_events or relation.get("dependent_event_id") in failed_events:
            relation["independent_error"] = False
            relation["dependency_note"] = "Relation failure is downstream of an event failure"


def _score_semantic_items(
    dimension: str, items: list[dict[str, Any]], id_key: str
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    weight = DIMENSION_WEIGHTS[dimension]
    if not items:
        return [], _summary(False, weight, None, 0.0, 0, 0), [], []
    importance_total = sum(_importance(item) for item in items)
    scored = []
    errors = []
    pending = []
    deduction_total = 0.0
    for item in items:
        current = dict(item)
        budget = weight * _importance(current) / importance_total
        verdict = _resolved_verdict(current)
        coefficient = STATUS_COEFFICIENTS[dimension].get(verdict, 0.0)
        suppression_reason = _duplicate_suppression(dimension, current)
        if suppression_reason:
            coefficient = 0.0
        accepted, needs_review, decision_reason = _accept_error(current, coefficient)
        deduction = budget * coefficient if accepted else 0.0
        current.update(
            {
                "resolved_verdict": verdict,
                "item_budget": round(budget, 4),
                "status_coefficient": coefficient,
                "deduction": round(deduction, 4),
                "deduction_accepted": accepted,
                "duplicate_suppressed": bool(suppression_reason),
                "suppression_reason": suppression_reason,
                "decision_reason": decision_reason,
                "review_required": needs_review,
            }
        )
        deduction_total += deduction
        if accepted and coefficient > 0:
            errors.append(_error_record(dimension, current, id_key))
        if needs_review:
            pending.append(_review_record(dimension, current, id_key))
        scored.append(current)
    deduction_total = min(weight, deduction_total)
    return scored, _summary(True, weight, weight - deduction_total, deduction_total, len(scored), len(errors)), errors, pending


def _score_delivery_items(
    dimension: str, items: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    weight = DIMENSION_WEIGHTS[dimension]
    scored = []
    errors = []
    pending = []
    deduction_total = 0.0
    for item in items:
        current = dict(item)
        candidate = DELIVERY_DEDUCTIONS[dimension].get(str(current.get("severity")), 0.0)
        accepted, needs_review, decision_reason = _accept_error(current, 1.0)
        deduction = candidate if accepted else 0.0
        current.update({"deduction": deduction, "deduction_accepted": accepted, "decision_reason": decision_reason, "review_required": needs_review})
        deduction_total += deduction
        if accepted:
            errors.append(_error_record(dimension, current, "issue_id"))
        if needs_review:
            pending.append(_review_record(dimension, current, "issue_id"))
        scored.append(current)
    deduction_total = min(weight, deduction_total)
    return scored, _summary(True, weight, weight - deduction_total, deduction_total, len(scored), len(errors)), errors, pending


def _accept_error(item: dict[str, Any], coefficient: float) -> tuple[bool, bool, str]:
    if coefficient <= 0:
        return False, False, "No independent deduction for this verdict"
    review = item.get("review") if isinstance(item.get("review"), dict) else {}
    decision = str(review.get("decision") or "uncertain")
    confidence = _confidence(review.get("confidence"))
    if decision == "invalid":
        return False, False, "Reviewer rejected the candidate error"
    if decision == "valid" and confidence >= MIN_REVIEW_CONFIDENCE:
        return True, False, "Reviewer confirmed the candidate error"
    return False, True, "Error remains unconfirmed and does not deduct automatically"


def _duplicate_suppression(dimension: str, item: dict[str, Any]) -> str | None:
    review = item.get("review") if isinstance(item.get("review"), dict) else {}
    if review.get("duplicate_of"):
        return f"Reviewer marked duplicate of {review['duplicate_of']}"
    if dimension == "event_preservation" and item.get("error_scope") == "anchor_only":
        return "Event loss is fully explained by an anchor error"
    if dimension == "relation_preservation" and item.get("independent_error") is False:
        return "Relation loss is fully explained by an event error"
    return None


def _resolved_verdict(item: dict[str, Any]) -> str:
    verdict = str(item.get("verdict") or "ambiguous").strip().lower()
    review = item.get("review") if isinstance(item.get("review"), dict) else {}
    resolved = str(review.get("resolved_verdict") or "").strip().lower()
    return resolved if verdict == "ambiguous" and resolved else verdict


def _summary(applicable: bool, weight: float, score: float | None, deduction: float, count: int, errors: int) -> dict[str, Any]:
    return {"applicable": applicable, "max_points": weight, "score": round(score, 2) if score is not None else None, "deduction": round(deduction, 2), "item_count": count, "error_count": errors}


def _error_record(dimension: str, item: dict[str, Any], id_key: str) -> dict[str, Any]:
    return {
        "error_ref": item.get("error_ref"),
        "dimension": dimension,
        "item_id": item.get(id_key),
        "verdict": item.get("resolved_verdict") or item.get("verdict") or item.get("issue_type"),
        "severity": item.get("severity") or _severity(_importance(item)),
        "deduction": item.get("deduction", 0.0),
        "source_evidence": item.get("source_span") or item.get("evidence_spans") or item.get("source_cues"),
        "target_evidence": item.get("target_spans") or item.get("target_span"),
        "reason": item.get("reason"),
        "review": item.get("review"),
    }


def _review_record(dimension: str, item: dict[str, Any], id_key: str) -> dict[str, Any]:
    return {"error_ref": item.get("error_ref"), "dimension": dimension, "item_id": item.get(id_key), "verdict": item.get("verdict") or item.get("issue_type"), "reason": item.get("reason")}


def _caps(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    caps = []
    for error in errors:
        dimension = error["dimension"]
        verdict = str(error.get("verdict") or "")
        severity = str(error.get("severity") or "")
        limit = None
        reason = None
        if dimension == "event_preservation" and verdict == "contradicted" and severity == "critical":
            limit, reason = 55.0, "critical_event_contradiction"
        elif dimension == "event_preservation" and verdict == "missing" and severity == "critical":
            limit, reason = 65.0, "critical_event_loss"
        elif dimension == "anchor_accuracy" and verdict == "incorrect" and severity == "critical":
            limit, reason = 65.0, "critical_anchor_error"
        elif dimension == "relation_preservation" and verdict == "reversed" and severity == "critical":
            limit, reason = 60.0, "critical_relation_reversal"
        elif dimension == "target_fluency" and severity == "critical":
            limit, reason = 60.0, "critical_unintelligibility"
        if limit is not None:
            caps.append({"error_ref": error.get("error_ref"), "reason": reason, "limit": limit, "confirmed": True})
    return caps


def _importance(item: dict[str, Any]) -> int:
    try:
        return min(3, max(1, int(item.get("importance", 2))))
    except (TypeError, ValueError):
        return 2


def _confidence(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _severity(importance: int) -> str:
    return {3: "critical", 2: "major", 1: "minor"}[importance]


def _dedupe(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output = []
    for row in rows:
        value = str(row.get(key) or "")
        if value and value not in seen:
            seen.add(value)
            output.append(row)
    return output
