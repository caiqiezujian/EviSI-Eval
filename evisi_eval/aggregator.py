from __future__ import annotations

from .models import EvaluationCard, FactVerdict
from .proposition_verifier import verify_proposition
from .verifier import verify_fact


DIMENSION_WEIGHTS = {
    "fact_accuracy": 35,
    "core_proposition_coverage": 25,
    "logic_relation_preservation": 20,
    "si_expression_adaptability": 12,
    "target_language_acceptability": 8,
}

CAP_LIMITS = {
    "critical_entity_mismatch": 60,
    "critical_polarity_error": 60,
    "critical_direction_error": 60,
    "critical_scope_error": 60,
    "critical_modality_error": 60,
    "critical_number_time_value_error": 70,
    "multiple_critical_facts": 55,
    "critical_proposition_loss": 55,
}


def evaluate_translation(card: EvaluationCard, system_name: str, si_translation: str) -> dict:
    verdicts = [verify_fact(fact, si_translation) for fact in card.facts]
    mode = card.metadata.get("evaluation_mode", "reference_assisted" if card.offline_translation else "source_only")
    prop_verdicts = [verify_proposition(prop, si_translation, mode) for prop in card.propositions]
    has_fact_error = any(v.verdict != "correct" for v in verdicts)
    scored_prop_verdicts = [] if has_fact_error else prop_verdicts
    critical_errors = [v for v in verdicts if v.importance == 3 and v.verdict != "correct"]
    cap_triggers = [v.cap_trigger for v in verdicts if v.cap_trigger]
    if len(critical_errors) >= 2:
        cap_triggers.append("multiple_critical_facts")
    if any(v.severity == "critical" and v.verdict == "missing_or_contradicted" for v in scored_prop_verdicts):
        cap_triggers.append("critical_proposition_loss")

    fact_deduction = min(sum(v.deduction for v in verdicts), DIMENSION_WEIGHTS["fact_accuracy"])
    prop_deduction = min(sum(v.deduction for v in scored_prop_verdicts), DIMENSION_WEIGHTS["core_proposition_coverage"])
    raw_score = 100 - fact_deduction - prop_deduction
    score_cap = min((CAP_LIMITS[t] for t in cap_triggers if t in CAP_LIMITS), default=None)
    final_score = min(raw_score, score_cap) if score_cap is not None else raw_score

    attributed_errors = [_error_record(v) for v in verdicts if v.verdict != "correct"]
    return {
        "sample_id": card.sample_id,
        "system_name": system_name,
        "evaluation_mode": mode,
        "evaluation_scope": ["fact_accuracy", "core_proposition_coverage"],
        "final_score": round(final_score, 2),
        "raw_score_before_caps": round(raw_score, 2),
        "dimension_scores": {
            "fact_accuracy": round(DIMENSION_WEIGHTS["fact_accuracy"] - fact_deduction, 2),
            "core_proposition_coverage": round(DIMENSION_WEIGHTS["core_proposition_coverage"] - prop_deduction, 2),
            "logic_relation_preservation": "not_evaluated_v0_1",
            "si_expression_adaptability": "not_evaluated_v0_1",
            "target_language_acceptability": "not_evaluated_v0_1",
        },
        "cap_triggered": score_cap is not None,
        "cap_reason": cap_triggers[0] if cap_triggers else None,
        "score_cap": score_cap,
        "fact_verdicts": [v.to_dict() for v in verdicts],
        "proposition_verdicts": [v.to_dict() for v in prop_verdicts],
        "attributed_errors": attributed_errors + [_prop_error_record(v) for v in scored_prop_verdicts if v.verdict != "covered" and v.deduction > 0],
        "non_penalized_items": [_suppressed_prop_record(v) for v in prop_verdicts if has_fact_error and v.verdict != "covered" and v.deduction > 0],
        "metadata": {
            "version": "0.2.0",
            "scoring_mode": "rules_fact_and_minimal_proposition",
            "attribution_policy": "fact_errors_suppress_overlapping_proposition_deductions",
            "review_required_count": sum(1 for v in verdicts if v.review_required) + sum(1 for v in prop_verdicts if v.review_required),
        },
    }


def _error_record(verdict: FactVerdict) -> dict:
    return {
        "error_id": f"e_{verdict.fact_id}",
        "dimension": "fact_accuracy",
        "item_id": verdict.fact_id,
        "error_type": _error_type(verdict),
        "severity": verdict.severity,
        "source_span": verdict.source_span,
        "target_span": verdict.translation_span,
        "deduction": verdict.deduction,
        "confidence": verdict.confidence,
        "review_status": "review_required" if verdict.review_required else "auto_accepted",
        "reason": verdict.reason,
        "cap_trigger": verdict.cap_trigger,
    }


def _error_type(verdict: FactVerdict) -> str:
    if verdict.verdict == "missing":
        return f"{verdict.type}_missing"
    if verdict.verdict == "ambiguous":
        return f"{verdict.type}_ambiguous"
    if verdict.type in {"number", "percentage", "money", "unit", "date_time"}:
        return "value_mismatch"
    if verdict.type in {"entity", "term"}:
        return "entity_or_term_mismatch"
    return f"{verdict.type}_distortion"


def _prop_error_record(verdict) -> dict:
    return {
        "error_id": f"e_{verdict.prop_id}",
        "dimension": "core_proposition_coverage",
        "item_id": verdict.prop_id,
        "error_type": verdict.verdict,
        "severity": verdict.severity,
        "source_span": verdict.source_span,
        "target_span": verdict.matched_target_span,
        "deduction": verdict.deduction,
        "confidence": verdict.confidence,
        "review_status": "review_required" if verdict.review_required else "auto_accepted",
        "reason": verdict.reason,
        "cap_trigger": "critical_proposition_loss" if verdict.severity == "critical" else None,
    }


def _suppressed_prop_record(verdict) -> dict:
    return {
        "type": "suppressed_proposition_error",
        "item_id": verdict.prop_id,
        "verdict": verdict.verdict,
        "reason": "fact-layer error already explains this candidate meaning loss; avoiding double deduction",
        "diagnostic_deduction_candidate": verdict.deduction,
    }
