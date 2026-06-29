from __future__ import annotations

import copy
from typing import Any


DIMENSION_WEIGHTS = {
    "fact_accuracy": 40.0,
    "core_proposition_coverage": 35.0,
    "logic_relation_preservation": 15.0,
    "target_language_comprehensibility": 10.0,
}

STATUS_COEFFICIENTS = {
    "fact_accuracy": {
        "exact": 0.0,
        "equivalent": 0.0,
        "incorrect": 1.0,
        "missing": 1.0,
        "ambiguous": 0.0,
    },
    "core_proposition_coverage": {
        "covered": 0.0,
        "compressed_covered": 0.0,
        "partially_covered": 0.5,
        "missing": 1.0,
        "contradicted": 1.0,
        "ambiguous": 0.0,
    },
    "logic_relation_preservation": {
        "preserved": 0.0,
        "weakened": 0.5,
        "missing": 1.0,
        "reversed": 1.0,
        "ambiguous": 0.0,
    },
}

TARGET_DEDUCTIONS = {"minor": 1.0, "major": 2.5, "critical": 5.0}
MIN_AUTO_CONFIDENCE = 0.75
HIGH_CONFIDENCE = 0.90


def aggregate_agent_result(agent_result: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(agent_result)
    dimension_scores: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    review_queue: list[dict[str, Any]] = []

    dimension_inputs = (
        ("fact_accuracy", result.get("fact_verdicts", []), "fact_id"),
        ("core_proposition_coverage", result.get("proposition_verdicts", []), "prop_id"),
        ("logic_relation_preservation", result.get("relation_verdicts", []), "relation_id"),
    )
    for dimension, items, id_key in dimension_inputs:
        scored, summary, dim_errors, dim_review = _score_weighted_items(
            dimension, items, id_key
        )
        result[_result_key(dimension)] = scored
        dimension_scores[dimension] = summary
        errors.extend(dim_errors)
        review_queue.extend(dim_review)

    target_items, target_summary, target_errors, target_review = _score_target_issues(
        result.get("target_quality_issues", [])
    )
    result["target_quality_issues"] = target_items
    dimension_scores["target_language_comprehensibility"] = target_summary
    errors.extend(target_errors)
    review_queue.extend(target_review)

    evaluated = [item for item in dimension_scores.values() if item["applicable"]]
    evaluated_weight = sum(float(item["max_points"]) for item in evaluated)
    earned_points = sum(float(item["score"]) for item in evaluated)
    normalized_score = 100.0 * earned_points / evaluated_weight if evaluated_weight else 0.0

    cap_candidates = _cap_candidates(errors)
    confirmed_caps = [item for item in cap_candidates if item["confirmed"]]
    if sum(1 for error in errors if error["severity"] == "critical" and error["review_valid"]) >= 2:
        confirmed_caps.append(
            {
                "reason": "multiple_confirmed_critical_errors",
                "limit": 55.0,
                "error_ref": None,
                "confirmed": True,
            }
        )
    score_cap = min((item["limit"] for item in confirmed_caps), default=None)
    final_score = min(normalized_score, score_cap) if score_cap is not None else normalized_score

    result.update(
        {
            "scoring_protocol": "evisi_llm_agent_v1.0",
            "dimension_weights": DIMENSION_WEIGHTS,
            "dimension_scores": dimension_scores,
            "evaluated_weight": round(evaluated_weight, 2),
            "score_before_caps": round(normalized_score, 2),
            "final_score": round(final_score, 2),
            "cap_triggered": score_cap is not None,
            "score_cap": score_cap,
            "cap_reasons": confirmed_caps,
            "cap_candidates": cap_candidates,
            "attributed_errors": errors,
            "review_queue": _dedupe_review_queue(review_queue),
        }
    )
    result["metadata"]["review_required_count"] = len(result["review_queue"])
    result["metadata"]["error_count"] = len(errors)
    result["metadata"]["aggregation_is_deterministic"] = True
    result["metadata"]["model_generated_final_score"] = False
    return result


def _score_weighted_items(
    dimension: str, items: list[dict[str, Any]], id_key: str
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    weight = DIMENSION_WEIGHTS[dimension]
    if not items:
        return [], {
            "applicable": False,
            "max_points": weight,
            "score": None,
            "deduction": 0.0,
            "reason": "No source item of this dimension exists in the frozen card",
        }, [], []

    importance_total = sum(_item_importance(item) for item in items)
    scored = []
    errors = []
    review_queue = []
    total_deduction = 0.0
    coefficients = STATUS_COEFFICIENTS[dimension]
    for item in items:
        current = dict(item)
        importance = _item_importance(current)
        budget = weight * importance / importance_total
        status = str(current.get("verdict") or "ambiguous").strip().lower()
        coefficient = coefficients.get(status, 0.0)
        duplicate_suppressed = False
        if dimension == "core_proposition_coverage" and current.get("required") is False:
            coefficient = 0.0
            duplicate_suppressed = True
        if dimension == "core_proposition_coverage" and current.get("error_scope") == "linked_fact_only":
            coefficient = 0.0
            duplicate_suppressed = True
        if dimension == "logic_relation_preservation" and current.get("independent_relation_error") is False:
            coefficient = 0.0
            duplicate_suppressed = True
        accepted, review_required, decision_reason = _accept_error(current, coefficient)
        deduction = budget * coefficient if accepted else 0.0
        severity = _severity_from_importance(importance) if coefficient else "none"
        current.update(
            {
                "item_budget": round(budget, 4),
                "status_coefficient": coefficient,
                "deduction": round(deduction, 4),
                "severity": severity,
                "deduction_accepted": accepted,
                "decision_reason": decision_reason,
                "review_required": review_required,
                "duplicate_suppressed": duplicate_suppressed,
            }
        )
        total_deduction += deduction
        if accepted and coefficient > 0:
            errors.append(_error_record(dimension, current, id_key))
        if review_required:
            review_queue.append(_review_record(dimension, current, id_key))
        scored.append(current)

    total_deduction = min(weight, total_deduction)
    summary = {
        "applicable": True,
        "max_points": weight,
        "score": round(weight - total_deduction, 2),
        "deduction": round(total_deduction, 2),
        "item_count": len(scored),
        "error_count": len(errors),
    }
    return scored, summary, errors, review_queue


def _score_target_issues(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    weight = DIMENSION_WEIGHTS["target_language_comprehensibility"]
    scored = []
    errors = []
    review_queue = []
    total_deduction = 0.0
    for item in items:
        current = dict(item)
        severity = str(current.get("severity") or "minor")
        candidate = TARGET_DEDUCTIONS.get(severity, 1.0)
        accepted, review_required, decision_reason = _accept_error(current, 1.0)
        deduction = candidate if accepted else 0.0
        current.update(
            {
                "deduction": deduction,
                "deduction_accepted": accepted,
                "decision_reason": decision_reason,
                "review_required": review_required,
            }
        )
        total_deduction += deduction
        if accepted:
            errors.append(_error_record("target_language_comprehensibility", current, "issue_id"))
        if review_required:
            review_queue.append(
                _review_record("target_language_comprehensibility", current, "issue_id")
            )
        scored.append(current)
    total_deduction = min(weight, total_deduction)
    return scored, {
        "applicable": True,
        "max_points": weight,
        "score": round(weight - total_deduction, 2),
        "deduction": round(total_deduction, 2),
        "item_count": len(scored),
        "error_count": len(errors),
    }, errors, review_queue


def _accept_error(item: dict[str, Any], coefficient: float) -> tuple[bool, bool, str]:
    status = str(item.get("verdict") or "")
    if status == "ambiguous":
        return False, True, "Ambiguous verdicts never deduct automatically"
    if coefficient <= 0:
        return False, False, "No error coefficient for this verdict"
    confidence = _confidence(item.get("confidence"))
    review = item.get("review") if isinstance(item.get("review"), dict) else None
    if review:
        decision = str(review.get("decision") or "uncertain")
        review_confidence = _confidence(review.get("confidence"))
        if decision == "invalid":
            return False, False, "Candidate error rejected by reviewer"
        if decision == "valid" and review_confidence >= MIN_AUTO_CONFIDENCE:
            return True, False, "Candidate error confirmed by reviewer"
        if decision == "uncertain" and confidence >= HIGH_CONFIDENCE and _item_importance(item) < 3:
            return True, True, "High-confidence non-critical error accepted; reviewer remained uncertain"
        return False, True, "Candidate error requires stronger review evidence"
    if confidence >= HIGH_CONFIDENCE and _item_importance(item) < 3:
        return True, True, "High-confidence non-critical error accepted without secondary review"
    return False, True, "Error is low-confidence or critical and requires review"


def _error_record(dimension: str, item: dict[str, Any], id_key: str) -> dict[str, Any]:
    item_id = item.get(id_key)
    source_span = item.get("source_span") or item.get("source_cues")
    error_type = item.get("error_type") or item.get("verdict")
    review = item.get("review") if isinstance(item.get("review"), dict) else {}
    return {
        "error_ref": item.get("error_ref"),
        "dimension": dimension,
        "item_id": item_id,
        "error_type": error_type,
        "item_type": item.get("type") or item.get("error_type"),
        "severity": item.get("severity", "minor"),
        "importance": _item_importance(item),
        "source_span": source_span,
        "target_span": item.get("target_span"),
        "confidence": _confidence(item.get("confidence")),
        "deduction": round(float(item.get("deduction", 0.0)), 4),
        "reason": item.get("reason"),
        "review": review or None,
        "review_valid": bool(
            review.get("decision") == "valid"
            and _confidence(review.get("confidence")) >= MIN_AUTO_CONFIDENCE
        ),
    }


def _review_record(dimension: str, item: dict[str, Any], id_key: str) -> dict[str, Any]:
    return {
        "error_ref": item.get("error_ref") or f"{id_key}:{item.get(id_key)}",
        "dimension": dimension,
        "item_id": item.get(id_key),
        "verdict": item.get("verdict") or item.get("error_type"),
        "confidence": _confidence(item.get("confidence")),
        "reason": item.get("decision_reason") or item.get("reason"),
    }


def _cap_candidates(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for error in errors:
        if error["importance"] < 3 and error["severity"] != "critical":
            continue
        dimension = error["dimension"]
        kind = str(error["error_type"])
        reason = None
        limit = None
        if dimension == "fact_accuracy":
            fact_type = str(error.get("item_type") or "")
            if kind == "incorrect" and fact_type in {
                "entity", "person", "org", "gpe", "location", "product", "event",
                "law_policy", "project",
            }:
                reason, limit = "confirmed_critical_entity_or_term_error", 60.0
            elif kind == "incorrect" and fact_type in {
                "number", "percent", "percentage", "money", "unit", "time", "date", "date_time",
            }:
                reason, limit = "confirmed_critical_value_error", 70.0
            elif kind == "incorrect" and fact_type in {"polarity", "direction", "scope", "modality"}:
                reason, limit = "confirmed_critical_boundary_or_stance_error", 60.0
            elif kind == "incorrect":
                reason, limit = "confirmed_critical_fact_error", 60.0
            elif kind == "missing":
                reason, limit = "confirmed_critical_fact_loss", 70.0
        elif dimension == "core_proposition_coverage":
            if kind == "contradicted":
                reason, limit = "confirmed_core_proposition_contradiction", 55.0
            elif kind == "missing":
                reason, limit = "confirmed_core_proposition_loss", 65.0
        elif dimension == "logic_relation_preservation" and kind == "reversed":
            reason, limit = "confirmed_critical_relation_reversal", 65.0
        elif dimension == "target_language_comprehensibility" and error["severity"] == "critical":
            reason, limit = "confirmed_unintelligible_output", 55.0
        if reason is not None:
            candidates.append(
                {
                    "reason": reason,
                    "limit": limit,
                    "error_ref": error["error_ref"],
                    "confirmed": error["review_valid"],
                }
            )
    return candidates


def _result_key(dimension: str) -> str:
    return {
        "fact_accuracy": "fact_verdicts",
        "core_proposition_coverage": "proposition_verdicts",
        "logic_relation_preservation": "relation_verdicts",
    }[dimension]


def _importance(value: Any) -> int:
    if isinstance(value, str):
        semantic = {"high": 3, "medium": 2, "low": 1}
        normalized = value.strip().lower()
        if normalized in semantic:
            return semantic[normalized]
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 1
    return min(3, max(1, parsed))


def _item_importance(item: dict[str, Any]) -> int:
    if "importance_numeric" in item:
        return _importance(item.get("importance_numeric"))
    return _importance(item.get("importance"))


def _confidence(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, parsed))


def _severity_from_importance(importance: int) -> str:
    return {1: "minor", 2: "major", 3: "critical"}[importance]


def _dedupe_review_queue(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for row in rows:
        key = row["error_ref"]
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output
