from __future__ import annotations

from evisi_eval.prompt_loader import PROMPT_FILES, load_prompt, prompt_manifest


def test_all_v05_prompts_are_registered_and_hashable() -> None:
    expected = {
        "source_evidence_agent", "alignment_agent", "target_evidence_agent",
        "fluency_agent", "si_expression_agent", "primary_judge_agent",
        "reviewer_agent", "adjudicator_agent", "summary_agent", "schema_repair",
    }
    assert set(PROMPT_FILES) >= expected
    manifest = prompt_manifest()
    assert set(manifest) == set(PROMPT_FILES)
    assert all(len(value) == 64 for value in manifest.values())


def test_all_v06_prompts_are_registered() -> None:
    expected = {
        "v06_source_segment_agent", "v06_source_anchor_agent",
        "v06_source_event_agent", "v06_source_relation_agent",
        "v06_target_alignment_agent", "v06_reference_anchor_projection_agent",
        "v06_reference_event_projection_agent", "v06_reference_relation_projection_agent",
        "v06_si_anchor_projection_agent", "v06_si_event_projection_agent",
        "v06_si_relation_projection_agent",
    }
    assert set(PROMPT_FILES) >= expected
    assert all(load_prompt(name).strip() for name in expected)


def test_v06_source_protocols_keep_auditable_extraction_rules() -> None:
    anchor = load_prompt("v06_source_anchor_agent")
    event = load_prompt("v06_source_event_agent")
    relation = load_prompt("v06_source_relation_agent")

    assert "三步判定决策树" in anchor
    assert "250,000 US dollars" in anchor
    assert "round-robin load balancing" in anchor
    assert "错误所有权" in anchor

    assert "结构化缩句算法" in event
    assert "问句" in event
    assert "Anchor Fidelity" in event
    assert "required_event_semantics" in event

    assert "Relation 成立的五道门" in relation
    assert "默认没有 Relation" in relation
    assert "问句后出现回答" in relation
    assert "blocked_by_event" in relation


def test_v06_projection_protocol_prevents_reference_string_scoring() -> None:
    si_anchor = load_prompt("v06_si_anchor_projection_agent")
    si_event = load_prompt("v06_si_event_projection_agent")
    si_relation = load_prompt("v06_si_relation_projection_agent")

    assert "Source 是唯一语义权威" in si_anchor
    assert "SI 与 Reference 不同绝不自动构成错误" in si_anchor
    assert "禁止生成 accepted_forms" in si_anchor
    assert "exact_value_unit" in si_anchor

    assert "Anchor 错误不能重复归 Event" in si_event
    assert "predicate_status" in si_event
    assert "argument_status" in si_event
    assert "operator_status" in si_event

    assert "端点依赖" in si_relation
    assert "mapping_status = not_scored" in si_relation
    assert "不要求译文使用同一连接词" in si_relation


def test_source_prompt_freezes_card_and_requires_importance() -> None:
    prompt = load_prompt("source_evidence_agent")
    assert "冻结" in prompt
    assert "importance" in prompt
    assert "系统译文" in prompt
    assert "source_card" not in prompt.casefold() or "源证据卡" in prompt


def test_target_prompt_declares_source_isolation() -> None:
    prompt = load_prompt("target_evidence_agent")
    assert "看不到源文" in prompt
    assert "target_units" in prompt
    assert "source_units" not in prompt
    assert "verdict" in prompt


def test_judge_reviewer_and_summary_contracts_are_separated() -> None:
    judge = load_prompt("primary_judge_agent")
    reviewer = load_prompt("reviewer_agent")
    summary = load_prompt("summary_agent")
    assert "不计算分数" in judge
    assert "看不到首轮" in reviewer
    assert "不能改" in summary or "禁止重新判定" in summary
    assert "final_score" in summary
