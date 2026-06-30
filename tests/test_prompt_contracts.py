from __future__ import annotations

from evisi_eval.prompt_loader import PROMPT_FILES, load_prompt, prompt_manifest


def test_all_v05_prompts_are_registered_and_hashable() -> None:
    expected = {
        "source_evidence_agent", "alignment_agent", "target_evidence_agent",
        "fluency_agent", "si_expression_agent", "primary_judge_agent",
        "reviewer_agent", "adjudicator_agent", "summary_agent", "schema_repair",
    }
    assert set(PROMPT_FILES) == expected
    manifest = prompt_manifest()
    assert set(manifest) == expected
    assert all(len(value) == 64 for value in manifest.values())


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


def test_source_and_target_load_the_same_conservative_semantic_protocol() -> None:
    source = load_prompt("source_evidence_agent")
    target = load_prompt("target_evidence_agent")
    shared_rules = [
        "默认没有 Relation",
        "问句后面出现回答",
        "无损/逐字",
        "可以从命题中剥离",
        "E-SPEECH",
        "必须归入以下 5 大类 13 子类",
    ]
    for rule in shared_rules:
        assert rule in source
        assert rule in target
    assert "没有合格 Relation 时必须输出" in source
    assert "没有合格 Relation 时必须输出" in target


def test_judge_reviewer_and_summary_contracts_are_separated() -> None:
    judge = load_prompt("primary_judge_agent")
    reviewer = load_prompt("reviewer_agent")
    summary = load_prompt("summary_agent")
    assert "不计算分数" in judge
    assert "看不到首轮" in reviewer
    assert "不能改" in summary or "禁止重新判定" in summary
    assert "final_score" in summary
