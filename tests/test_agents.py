"""Behavior tests for the v0.5 evidence-agent workflow."""

from __future__ import annotations

import json

from evisi_eval.agents import EvaluationAgentLoop, SourceCardAgent, TargetEvidenceAgent
from evisi_eval.llm_provider import ScriptedLLMClient


def source_response() -> dict:
    return {
        "sample_id": "s1",
        "source_units": [{"source_unit_id": "S1", "source_unit": "Mark left."}],
        "source_anchors": [{
            "source_unit_id": "S1", "source_anchor_id": "SA1",
            "anchor_type": "A-ENT",
            "anchor_text": "Mark", "normalized_meaning": "Mark",
            "evidence_span": "Mark", "importance": 2,
        }],
        "source_events": [{
            "source_unit_id": "S1", "source_event_id": "SE1",
            "event_type": "E-ACT",
            "event_text": "Mark left", "canonical_meaning": "Mark left",
            "evidence_span": "Mark left", "importance": 3,
        }],
        "source_relations": [],
    }


def alignment_response(translation: str = "马克离开了。") -> dict:
    return {
        "sample_id": "s1", "system_name": "anonymous_system",
        "eval_units": [{
            "eval_unit_id": "E1", "source_unit_ids": ["S1"],
            "target_unit": translation, "alignment_status": "aligned",
            "reason": "语义对应",
        }],
    }


def target_response() -> dict:
    return {
        "sample_id": "s1", "system_name": "anonymous_system",
        "target_anchors": [{
            "eval_unit_id": "E1", "target_anchor_id": "TA1",
            "anchor_type": "A-ENT",
            "anchor_text": "马克", "normalized_meaning": "Mark", "evidence_span": "马克",
        }],
        "target_events": [{
            "eval_unit_id": "E1", "target_event_id": "TE1",
            "event_type": "E-ACT",
            "event_text": "马克离开了", "canonical_meaning": "Mark left",
            "evidence_span": "马克离开了",
        }],
        "target_relations": [],
    }


def fluency_response() -> dict:
    return {"fluency_issues": [], "fluency_assessment": "清楚自然。"}


def expression_response() -> dict:
    return {"si_expression_issues": [], "si_expression_assessment": "表达高效。"}


def judgement_response(anchor_verdict: str = "correct", confidence: float = 0.95) -> dict:
    return {
        "anchor_judgements": [{
            "judgement_id": "AJ1", "source_anchor_id": "SA1",
            "source_evidence_spans": ["Mark"], "eval_unit_ids": ["E1"],
            "target_anchor_ids": ["TA1"], "target_evidence_spans": ["马克"],
            "verdict": anchor_verdict, "confidence": confidence,
            "reason": "姓名语义比较结果。",
        }],
        "event_judgements": [{
            "judgement_id": "EJ1", "source_event_id": "SE1",
            "source_evidence_spans": ["Mark left"], "eval_unit_ids": ["E1"],
            "target_event_ids": ["TE1"], "target_evidence_spans": ["马克离开了"],
            "verdict": "correct", "confidence": 0.96,
            "reason": "主体与动作完整保留。",
        }],
        "relation_judgements": [],
    }


def adjudication_response(verdict: str = "correct") -> dict:
    return {"adjudications": [{
        "judgement_id": "AJ1", "source_anchor_id": "SA1",
        "source_evidence_spans": ["Mark"], "eval_unit_ids": ["E1"],
        "target_anchor_ids": ["TA1"], "target_evidence_spans": ["马克"],
        "verdict": verdict, "confidence": 0.91,
        "reason": "裁决后确认姓名等价。",
    }]}


def summary_response() -> dict:
    return {"score_summary": {
        "overall_judgement": "内容准确，表达清楚。",
        "main_strengths": ["AJ1、EJ1 正确"],
        "main_errors": [], "uncertain_points": [],
    }}


def sample() -> dict:
    return {
        "sample_id": "s1", "source_text": "Mark left.",
        "reference_translation": "马克离开了。", "src_lang": "en", "tgt_lang": "zh",
    }


def output(system_name: str = "system_a") -> dict:
    return {"sample_id": "s1", "system_name": system_name, "si_translation": "马克离开了。"}


def build_card() -> tuple[dict, ScriptedLLMClient]:
    client = ScriptedLLMClient([source_response()])
    card, _ = SourceCardAgent(client).build(sample())
    return card, client


def test_end_to_end_agreement_produces_deterministic_score() -> None:
    card, _ = build_card()
    primary = ScriptedLLMClient([
        alignment_response(), target_response(), fluency_response(), expression_response(),
        judgement_response(), summary_response(),
    ], provider="primary", model="judge-a")
    reviewer = ScriptedLLMClient([judgement_response()], provider="review", model="judge-b")

    result, artifacts = EvaluationAgentLoop(primary, reviewer).run(card, output())

    assert result["final_score"] == 100.0
    assert result["score_status"] == "final"
    assert result["review"]["independent_model"] is True
    assert result["review"]["disagreement_count"] == 0
    assert result["anchor_judgements"][0]["resolution"] == "primary_reviewer_agreement"
    assert "target_eval_cards" in artifacts
    assert [call["task"] for call in primary.calls] == [
        "alignment_agent", "target_evidence_agent", "fluency_agent",
        "si_expression_agent", "primary_judge_agent", "summary_agent",
    ]


def test_target_evidence_agent_cannot_see_source() -> None:
    card, _ = build_card()
    primary = ScriptedLLMClient([
        alignment_response(), target_response(), fluency_response(), expression_response(),
        judgement_response(), summary_response(),
    ])
    reviewer = ScriptedLLMClient([judgement_response()])

    EvaluationAgentLoop(primary, reviewer).run(card, output())
    call = next(row for row in primary.calls if row["task"] == "target_evidence_agent")
    payload = json.dumps(call["payload"], ensure_ascii=False)
    assert set(call["payload"]) == {"sample_id", "system_name", "target_units"}
    assert "Mark left." not in payload
    assert "source_" not in payload


def test_reviewer_is_blind_to_primary_and_real_system_name() -> None:
    card, _ = build_card()
    primary = ScriptedLLMClient([
        alignment_response(), target_response(), fluency_response(), expression_response(),
        judgement_response(), summary_response(),
    ])
    reviewer = ScriptedLLMClient([judgement_response()])

    EvaluationAgentLoop(primary, reviewer).run(card, output("RealSystem42"))
    review_call = reviewer.calls[0]
    payload = json.dumps(review_call["payload"], ensure_ascii=False)
    assert review_call["task"] == "reviewer_agent"
    assert "primary" not in payload.casefold()
    assert "judgement" not in payload.casefold()
    assert "RealSystem42" not in payload


def test_disagreement_triggers_adjudication() -> None:
    card, _ = build_card()
    primary = ScriptedLLMClient([
        alignment_response(), target_response(), fluency_response(), expression_response(),
        judgement_response("correct"), summary_response(),
    ], provider="primary", model="judge-a")
    reviewer = ScriptedLLMClient([
        judgement_response("incorrect"), adjudication_response("correct")
    ], provider="review", model="judge-b")

    result, _ = EvaluationAgentLoop(primary, reviewer).run(card, output())

    assert [call["task"] for call in reviewer.calls] == ["reviewer_agent", "adjudicator_agent"]
    assert result["review"]["disagreement_count"] == 1
    assert result["review"]["adjudication_count"] == 1
    assert result["anchor_judgements"][0]["resolution"] == "adjudicated"
    assert result["anchor_judgements"][0]["verdict"] == "correct"


def test_reference_and_real_system_name_do_not_leak() -> None:
    source_client = ScriptedLLMClient([source_response()])
    card, _ = SourceCardAgent(source_client).build(sample())
    assert "reference_translation" not in source_client.calls[0]["payload"]

    primary = ScriptedLLMClient([
        alignment_response(), target_response(), fluency_response(), expression_response(),
        judgement_response(), summary_response(),
    ])
    reviewer = ScriptedLLMClient([judgement_response()])
    EvaluationAgentLoop(primary, reviewer).run(card, output("SecretSystem"))
    for call in primary.calls + reviewer.calls:
        serialized = json.dumps(call["payload"], ensure_ascii=False)
        assert "SecretSystem" not in serialized
        assert "reference_translation" not in serialized


def test_target_evidence_whitespace_is_mapped_back_to_verbatim_text() -> None:
    client = ScriptedLLMClient([{
        "target_anchors": [{
            "eval_unit_id": "E1", "target_anchor_id": "TA1", "anchor_type": "A-ENT",
            "anchor_text": "马克", "normalized_meaning": "Mark", "evidence_span": "马 克",
        }],
        "target_events": [], "target_relations": [],
    }])
    result = TargetEvidenceAgent(client).analyze(
        "s1", [{"eval_unit_id": "E1", "target_unit": "马克离开了。"}]
    )
    assert result.artifact["target_anchors"][0]["evidence_span"] == "马克"
    assert result.normalization_notes == [
        "TA1 evidence_span mapped to verbatim target text"
    ]
    assert len(client.calls) == 1


def test_target_relation_evidence_whitespace_is_mapped_to_selected_unit() -> None:
    client = ScriptedLLMClient([{
        "target_anchors": [],
        "target_events": [
            {"eval_unit_id": "E1", "target_event_id": "TE1", "event_type": "E-STATE",
             "event_text": "原因存在", "canonical_meaning": "原因存在", "evidence_span": "原因"},
            {"eval_unit_id": "E3", "target_event_id": "TE2", "event_type": "E-STATE",
             "event_text": "结果存在", "canonical_meaning": "结果存在", "evidence_span": "结果"},
        ],
        "target_relations": [{
            "target_relation_id": "TR1", "relation_type": "cause_effect",
            "relation_basis": "strong_semantic_entailment", "relation_cue": "",
            "confidence": 0.9,
            "eval_unit_ids": ["E1", "E3"], "relation_text": "原因导致结果",
            "relation_meaning": "因果关系", "evidence_spans": ["原 因", "结 果"],
            "related_target_event_ids": ["TE1", "TE2"],
        }],
    }])
    result = TargetEvidenceAgent(client).analyze("s1", [
        {"eval_unit_id": "E1", "target_unit": "原因。"},
        {"eval_unit_id": "E2", "target_unit": "插入说明。"},
        {"eval_unit_id": "E3", "target_unit": "结果。"},
    ])
    relation = result.artifact["target_relations"][0]
    assert relation["evidence_spans"] == ["原因", "结果"]
    assert result.normalization_notes == [
        "TR1 evidence_spans mapped to verbatim target text"
    ]
