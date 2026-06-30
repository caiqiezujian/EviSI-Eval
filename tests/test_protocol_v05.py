from __future__ import annotations

from evisi_eval.validation import (
    calculate_scores,
    validate_delivery_artifact,
    validate_judgement_artifact,
    validate_source_card_artifact,
)


def test_source_card_requires_explicit_arrays_and_importance() -> None:
    artifact = {
        "source_units": [{"source_unit_id": "S1", "source_unit": "Mark left."}],
        "source_anchors": [{
            "source_unit_id": "S1", "source_anchor_id": "SA1",
            "anchor_type": "A-ENT",
            "anchor_text": "Mark", "normalized_meaning": "Mark", "evidence_span": "Mark",
        }],
        "source_events": [],
    }
    issues = validate_source_card_artifact(artifact, "Mark left.")
    assert "source_relations must be an array" in issues
    assert any("importance" in issue for issue in issues)


def test_judgement_rejects_non_local_target_evidence() -> None:
    source_card = {
        "source_anchors": [{
            "source_unit_id": "S1", "source_anchor_id": "SA1",
            "anchor_type": "A-ENT",
            "anchor_text": "Mark", "normalized_meaning": "Mark",
            "evidence_span": "Mark", "importance": 2,
        }],
        "source_events": [], "source_relations": [],
    }
    target_card = {
        "eval_units": [
            {"eval_unit_id": "E1", "source_unit_ids": ["S1"], "target_unit": "甲"},
            {"eval_unit_id": "E2", "source_unit_ids": ["S2"], "target_unit": "乙"},
            {"eval_unit_id": "E3", "source_unit_ids": ["S3"], "target_unit": "马克"},
        ],
        "target_anchors": [{
            "eval_unit_id": "E3", "target_anchor_id": "TA1",
            "anchor_type": "A-ENT",
            "anchor_text": "马克", "normalized_meaning": "Mark", "evidence_span": "马克",
        }],
        "target_events": [], "target_relations": [],
    }
    judgement = {
        "anchor_judgements": [{
            "judgement_id": "AJ1", "source_anchor_id": "SA1",
            "source_evidence_spans": ["Mark"], "eval_unit_ids": ["E3"],
            "target_anchor_ids": ["TA1"], "target_evidence_spans": ["马克"],
            "verdict": "correct", "confidence": 0.9, "reason": "错误的全篇搜索",
        }],
        "event_judgements": [], "relation_judgements": [],
    }
    issues = validate_judgement_artifact(judgement, source_card, target_card)
    assert any("non-local" in issue for issue in issues)


def test_importance_weighting_and_uncertain_coverage_are_deterministic() -> None:
    source_card = {
        "source_anchors": [
            {"source_anchor_id": "SA1", "importance": 3},
            {"source_anchor_id": "SA2", "importance": 1},
        ],
        "source_events": [], "source_relations": [],
    }
    judgements = {
        "anchor_judgements": [
            {"source_anchor_id": "SA1", "verdict": "correct", "confidence": 0.95},
            {"source_anchor_id": "SA2", "verdict": "uncertain", "confidence": 0.80},
        ],
        "event_judgements": [], "relation_judgements": [],
    }
    result = calculate_scores(judgements, [], [], source_card)
    diagnostic = result["score_diagnostics"]["anchor_fidelity"]
    assert result["dimension_scores"]["anchor_fidelity"] == 100.0
    assert diagnostic["coverage"] == 75.0
    assert diagnostic["uncertain_importance_weight"] == 1
    assert result["score_status"] == "provisional_review_required"


def test_all_uncertain_items_produce_no_decisions_instead_of_zero() -> None:
    source_card = {
        "source_anchors": [{"source_anchor_id": "SA1", "importance": 3}],
        "source_events": [], "source_relations": [],
    }
    judgements = {
        "anchor_judgements": [
            {"source_anchor_id": "SA1", "verdict": "uncertain", "confidence": 0.80}
        ],
        "event_judgements": [], "relation_judgements": [],
    }
    result = calculate_scores(judgements, [], [], source_card)
    diagnostic = result["score_diagnostics"]["anchor_fidelity"]
    assert result["dimension_scores"]["anchor_fidelity"] is None
    assert diagnostic["decision_status"] == "no_decisions"
    assert diagnostic["coverage"] == 0.0
    assert result["final_score"] is None
    assert result["score_status"] == "provisional_no_decisions"


def test_delivery_validation_rejects_duplicate_penalty_span() -> None:
    artifact = {
        "fluency_issues": [
            {"issue_id": "F1", "issue_type": "fragment", "target_span": "嗯",
             "severity": "minor", "reason": "第一项"},
            {"issue_id": "F2", "issue_type": "filler", "target_span": "嗯",
             "severity": "moderate", "reason": "重复处罚"},
        ],
        "fluency_assessment": "存在问题",
    }
    issues = validate_delivery_artifact(
        artifact, "嗯，然后继续。", "fluency_issues", "fluency_assessment", "F"
    )
    assert any("duplicates" in issue for issue in issues)


def test_non_applicable_relation_weight_is_renormalized() -> None:
    source_card = {
        "source_anchors": [{"source_anchor_id": "SA1", "importance": 3}],
        "source_events": [{"source_event_id": "SE1", "importance": 3}],
        "source_relations": [],
    }
    judgements = {
        "anchor_judgements": [
            {"source_anchor_id": "SA1", "verdict": "missing", "confidence": 0.95}
        ],
        "event_judgements": [
            {"source_event_id": "SE1", "verdict": "correct", "confidence": 0.95}
        ],
        "relation_judgements": [],
    }
    result = calculate_scores(judgements, [], [], source_card)
    assert result["score_diagnostics"]["relation_fidelity"]["applicable"] is False
    assert result["effective_dimension_weights"]["relation_fidelity"] == 0.0
    assert result["final_score"] == 62.5
