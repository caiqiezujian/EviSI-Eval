from __future__ import annotations

from evisi_eval.validation import (
    calculate_scores,
    validate_delivery_artifact,
    validate_judgement_artifact,
    validate_source_card_artifact,
    validate_target_evidence_artifact,
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


def test_unknown_target_item_is_reported_without_crashing() -> None:
    source_card = {
        "source_anchors": [{
            "source_unit_id": "S1", "source_anchor_id": "SA1", "anchor_type": "A-ENT",
            "anchor_text": "Mark", "normalized_meaning": "Mark",
            "evidence_span": "Mark", "importance": 2,
        }],
        "source_events": [], "source_relations": [],
    }
    target_card = {
        "eval_units": [{
            "eval_unit_id": "E1", "source_unit_ids": ["S1"], "target_unit": "马克"
        }],
        "target_anchors": [], "target_events": [], "target_relations": [],
    }
    judgement = {
        "anchor_judgements": [{
            "judgement_id": "AJ1", "source_anchor_id": "SA1",
            "source_evidence_spans": ["Mark"], "eval_unit_ids": ["E1"],
            "target_anchor_ids": ["TA404"], "target_evidence_spans": ["马克"],
            "verdict": "correct", "confidence": 0.9, "reason": "invalid reference",
        }],
        "event_judgements": [], "relation_judgements": [],
    }
    issues = validate_judgement_artifact(judgement, source_card, target_card)
    assert any("unknown target item" in issue for issue in issues)


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


def test_non_contiguous_ordered_relation_units_are_valid() -> None:
    target_units = [
        {"eval_unit_id": "E1", "target_unit": "原因。"},
        {"eval_unit_id": "E2", "target_unit": "插入说明。"},
        {"eval_unit_id": "E3", "target_unit": "结果。"},
    ]
    artifact = {
        "target_anchors": [],
        "target_events": [
            {"eval_unit_id": "E1", "target_event_id": "TE1", "event_type": "E-STATE",
             "event_text": "原因", "canonical_meaning": "原因存在", "evidence_span": "原因"},
            {"eval_unit_id": "E3", "target_event_id": "TE2", "event_type": "E-STATE",
             "event_text": "结果", "canonical_meaning": "结果存在", "evidence_span": "结果"},
        ],
        "target_relations": [{
            "target_relation_id": "TR1", "relation_type": "cause_effect",
            "relation_basis": "strong_semantic_entailment", "relation_cue": "",
            "confidence": 0.9,
            "eval_unit_ids": ["E1", "E3"],
            "relation_text": "原因导致结果", "relation_meaning": "因果关系",
            "evidence_spans": ["原因", "结果"], "related_target_event_ids": ["TE1", "TE2"],
        }],
    }
    assert validate_target_evidence_artifact(artifact, target_units) == []

    artifact["target_relations"][0]["eval_unit_ids"] = ["E3", "E1"]
    issues = validate_target_evidence_artifact(artifact, target_units)
    assert any("unique and ordered" in issue for issue in issues)


def test_empty_relations_are_valid_and_weak_implicit_relations_are_rejected() -> None:
    target_units = [
        {"eval_unit_id": "E1", "target_unit": "甲发生。"},
        {"eval_unit_id": "E2", "target_unit": "乙发生。"},
    ]
    events = [
        {"eval_unit_id": "E1", "target_event_id": "TE1", "event_type": "E-ACT",
         "event_text": "甲发生", "canonical_meaning": "甲发生", "evidence_span": "甲发生"},
        {"eval_unit_id": "E2", "target_event_id": "TE2", "event_type": "E-ACT",
         "event_text": "乙发生", "canonical_meaning": "乙发生", "evidence_span": "乙发生"},
    ]
    empty = {"target_anchors": [], "target_events": events, "target_relations": []}
    assert validate_target_evidence_artifact(empty, target_units) == []

    weak = {
        "target_anchors": [], "target_events": events,
        "target_relations": [{
            "target_relation_id": "TR1", "relation_type": "cause_effect",
            "relation_basis": "strong_semantic_entailment", "relation_cue": "",
            "confidence": 0.6, "eval_unit_ids": ["E1", "E2"],
            "relation_text": "甲导致乙", "relation_meaning": "因果关系",
            "evidence_spans": ["甲发生", "乙发生"],
            "related_target_event_ids": ["TE1", "TE2"],
        }],
    }
    issues = validate_target_evidence_artifact(weak, target_units)
    assert any("confidence must be at least 0.85" in issue for issue in issues)
