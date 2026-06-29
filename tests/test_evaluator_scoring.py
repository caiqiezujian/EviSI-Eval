from evisi_eval.evaluator import evaluate_translation
from evisi_eval.llm_provider import ScriptedLLMClient
from evisi_eval.scoring import score_evaluation
from evisi_eval.validation import validate_sentence_alignment, validate_target_analysis


def _card():
    return {
        "sample_id": "s1",
        "source_text": "Mark invested 20 million dollars.",
        "offline_translation": None,
        "src_lang": "en",
        "tgt_lang": "zh",
        "sentences": [{"sentence_id": "S1", "sentence_text": "Mark invested 20 million dollars.", "anchor_ids": ["A1"]}],
        "anchors": [{"anchor_id": "A1", "sentence_id": "S1", "source_span": "20 million dollars", "normalized_value": "USD 20000000", "anchor_type": "MONEY", "role_hint": "quantity", "attributes": {}, "importance": 3, "required": True, "confidence": 0.9}],
        "events": [{"event_id": "V1", "sentence_id": "S1", "evidence_spans": ["Mark invested 20 million dollars"], "canonical_meaning": "Mark invested USD 20 million", "predicate": "invest", "arguments": [], "linked_anchor_ids": ["A1"], "attributes": {"polarity": "positive"}, "importance": 3, "required": True, "confidence": 0.9}],
        "relations": [],
        "allowed_omissions": [],
        "metadata": {"card_hash": "hash", "card_status": "machine_validated"},
    }


def test_evidence_alignment_and_double_penalty_suppression():
    translation = "马克投资了两百万美元。这个这个投资已经完成。"
    primary = ScriptedLLMClient(
        [
            {"target_units": [{"unit_id": "T1", "unit_text": "马克投资了两百万美元。"}, {"unit_id": "T2", "unit_text": "这个这个投资已经完成。"}], "sentence_alignments": [{"source_sentence_id": "S1", "source_sentence_text": "Mark invested 20 million dollars.", "target_unit_ids": ["T1", "T2"], "target_spans": ["马克投资了两百万美元。", "这个这个投资已经完成。"], "alignment_type": "one_to_many", "group_id": None, "confidence": 0.95, "reason": "one source sentence expanded into two target units"}], "unaligned_target_unit_ids": []},
            {"target_units": [{"unit_id": "T1", "unit_text": "马克投资了两百万美元。"}, {"unit_id": "T2", "unit_text": "这个这个投资已经完成。"}], "target_anchors": [{"target_anchor_id": "TA1", "unit_id": "T1", "target_span": "两百万美元", "normalized_value": "USD 2000000", "anchor_type": "MONEY", "attributes": {}, "confidence": 0.9}], "target_events": [{"target_event_id": "TV1", "unit_ids": ["T1"], "evidence_spans": ["马克投资了两百万美元"], "canonical_meaning": "Mark invested USD 2 million", "predicate": "invest", "arguments": [], "attributes": {"polarity": "positive"}, "confidence": 0.9}], "target_relations": []},
            {"anchor_alignments": [{"anchor_id": "A1", "target_anchor_ids": ["TA1"], "target_unit_ids": ["T1"], "target_spans": ["两百万美元"], "verdict": "incorrect", "confidence": 0.98, "reason": "amount changed"}], "event_alignments": [{"event_id": "V1", "target_event_ids": ["TV1"], "target_unit_ids": ["T1"], "target_spans": ["马克投资了两百万美元"], "verdict": "partially_covered", "error_scope": "anchor_only", "attribute_errors": [], "confidence": 0.95, "reason": "only linked amount is wrong"}], "relation_alignments": []},
            {"fluency_issues": [], "efficiency_issues": [{"issue_id": "F1", "issue_type": "meaningless_repetition", "target_span": "这个这个", "severity": "minor", "confidence": 0.9, "reason": "immediate repetition", "listener_impact": "minor disruption"}]},
        ]
    )
    review = ScriptedLLMClient(
        [{"decisions": [
            {"error_ref": "anchor_id:A1", "decision": "valid", "resolved_verdict": None, "counterevidence_spans": [], "duplicate_of": None, "confidence": 0.95, "reason": "wrong amount"},
            {"error_ref": "event_id:V1", "decision": "valid", "resolved_verdict": None, "counterevidence_spans": [], "duplicate_of": "anchor_id:A1", "confidence": 0.95, "reason": "same amount error"},
            {"error_ref": "issue_id:F1", "decision": "valid", "resolved_verdict": None, "counterevidence_spans": [], "duplicate_of": None, "confidence": 0.9, "reason": "concrete repetition"},
        ]}]
    )
    evaluated = evaluate_translation(_card(), "anonymous", translation, primary, review)
    result = score_evaluation(evaluated)
    assert result["dimension_scores"]["anchor_accuracy"]["score"] == 0
    assert result["dimension_scores"]["event_preservation"]["score"] == 40
    assert result["event_alignments"][0]["duplicate_suppressed"] is True
    assert result["score_cap"] == 65.0


def test_unreviewed_error_does_not_deduct():
    evaluation = {
        "metadata": {},
        "anchor_alignments": [{"anchor_id": "A1", "importance": 3, "verdict": "missing", "error_ref": "anchor_id:A1", "review": {"decision": "uncertain", "confidence": 0.0}}],
        "event_alignments": [],
        "relation_alignments": [],
        "fluency_issues": [],
        "efficiency_issues": [],
    }
    result = score_evaluation(evaluation)
    assert result["dimension_scores"]["anchor_accuracy"]["score"] == 30
    assert result["review_queue"][0]["error_ref"] == "anchor_id:A1"


def test_relation_failure_downstream_of_event_is_not_double_penalized():
    evaluation = {
        "metadata": {},
        "anchor_alignments": [],
        "event_alignments": [{"event_id": "V1", "importance": 3, "verdict": "missing", "error_scope": "event_only", "error_ref": "event_id:V1", "review": {"decision": "valid", "confidence": 0.95}}],
        "relation_alignments": [{"relation_id": "R1", "head_event_id": "V1", "dependent_event_id": "V2", "importance": 3, "verdict": "missing", "independent_error": True, "error_ref": "relation_id:R1", "review": {"decision": "valid", "confidence": 0.95}}],
        "fluency_issues": [],
        "efficiency_issues": [],
    }
    result = score_evaluation(evaluation)
    assert result["dimension_scores"]["event_preservation"]["score"] == 0
    assert result["dimension_scores"]["relation_preservation"]["score"] == 10
    assert result["relation_alignments"][0]["duplicate_suppressed"] is True


def test_target_relation_contract_is_validated():
    translation = "需求恢复，因此销售额增长。"
    analysis = {
        "target_units": [{"unit_id": "T1", "unit_text": translation}],
        "target_anchors": [],
        "target_events": [
            {"target_event_id": "TV1", "unit_ids": ["T1"], "evidence_spans": ["需求恢复"], "canonical_meaning": "demand recovered", "predicate": "recover", "arguments": [], "attributes": {}, "confidence": 0.9},
            {"target_event_id": "TV2", "unit_ids": ["T1"], "evidence_spans": ["销售额增长"], "canonical_meaning": "sales increased", "predicate": "increase", "arguments": [], "attributes": {}, "confidence": 0.9},
        ],
        "target_relations": [{"target_relation_id": "TR1", "relation_type": "cause", "head_target_event_id": "TV1", "dependent_target_event_id": "TV2", "target_cues": ["因此"], "canonical_meaning": "TV1 causes TV2", "confidence": 0.9}],
    }
    assert not validate_target_analysis(analysis, translation)
    analysis["target_relations"][0]["dependent_target_event_id"] = "TV9"
    assert any("unknown target event" in issue for issue in validate_target_analysis(analysis, translation))


def test_many_to_one_sentence_alignment_requires_shared_group():
    source = [
        {"sentence_id": "S1", "sentence_text": "Demand recovered."},
        {"sentence_id": "S2", "sentence_text": "Sales increased."},
    ]
    translation = "需求恢复后，销售额增长。"
    alignment = {
        "target_units": [{"unit_id": "T1", "unit_text": translation}],
        "sentence_alignments": [
            {"source_sentence_id": "S1", "source_sentence_text": "Demand recovered.", "target_unit_ids": ["T1"], "target_spans": [translation], "alignment_type": "many_to_one", "group_id": "G1", "confidence": 0.9, "reason": "compressed"},
            {"source_sentence_id": "S2", "source_sentence_text": "Sales increased.", "target_unit_ids": ["T1"], "target_spans": [translation], "alignment_type": "many_to_one", "group_id": "G1", "confidence": 0.9, "reason": "compressed"},
        ],
        "unaligned_target_unit_ids": [],
    }
    assert not validate_sentence_alignment(alignment, source, translation)
    alignment["sentence_alignments"][1]["group_id"] = "G2"
    assert any("many_to_one group" in issue for issue in validate_sentence_alignment(alignment, source, translation))


def test_semantically_empty_target_analysis_is_repaired_before_scoring():
    translation = "马克投资了两千万美元。"
    sentence_alignment = {
        "target_units": [{"unit_id": "T1", "unit_text": translation}],
        "sentence_alignments": [{"source_sentence_id": "S1", "source_sentence_text": "Mark invested 20 million dollars.", "target_unit_ids": ["T1"], "target_spans": [translation], "alignment_type": "one_to_one", "group_id": None, "confidence": 0.98, "reason": "clear correspondence"}],
        "unaligned_target_unit_ids": [],
    }
    repaired_target = {
        "target_units": [{"unit_id": "T1", "unit_text": translation}],
        "target_anchors": [{"target_anchor_id": "TA1", "unit_id": "T1", "target_span": "两千万美元", "normalized_value": "USD 20000000", "anchor_type": "MONEY", "attributes": {}, "confidence": 0.95}],
        "target_events": [{"target_event_id": "TV1", "unit_ids": ["T1"], "evidence_spans": ["马克投资了两千万美元"], "canonical_meaning": "Mark invested USD 20 million", "predicate": "invest", "arguments": [], "attributes": {}, "confidence": 0.95}],
        "target_relations": [],
    }
    primary = ScriptedLLMClient([
        sentence_alignment,
        {"target_units": [{"unit_id": "T1", "unit_text": translation}], "target_anchors": [], "target_events": [], "target_relations": []},
        repaired_target,
        {"anchor_alignments": [{"anchor_id": "A1", "target_anchor_ids": ["TA1"], "target_unit_ids": ["T1"], "target_spans": ["两千万美元"], "verdict": "exact", "confidence": 0.98, "reason": "amount preserved"}], "event_alignments": [{"event_id": "V1", "target_event_ids": ["TV1"], "target_unit_ids": ["T1"], "target_spans": ["马克投资了两千万美元"], "verdict": "covered", "error_scope": "none", "attribute_errors": [], "confidence": 0.98, "reason": "event preserved"}], "relation_alignments": []},
        {"fluency_issues": [], "efficiency_issues": []},
    ])
    evaluated = evaluate_translation(_card(), "anonymous", translation, primary, ScriptedLLMClient([]))
    assert evaluated["target_analysis"]["target_anchors"]
    assert "semantically empty" in evaluated["metadata"]["target_validation_issues_before_repair"][0]
    assert any(call["task"] == "repair_target_analysis" for call in primary.calls)
