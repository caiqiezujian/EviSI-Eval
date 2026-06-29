from evisi_eval.prompt_loader import PROMPT_FILES, load_prompt


def test_all_sixteen_protocol_prompts_and_repair_prompt_exist():
    assert len(PROMPT_FILES) == 17
    for name in PROMPT_FILES:
        prompt = load_prompt(name)
        assert prompt.strip()
        assert "JSON" in prompt or name == "schema_repair"


def test_prompt_isolation_and_scoring_constraints_are_explicit():
    assert "不看任何系统译文" in load_prompt("source_anchor_extraction")
    assert "不看源文" in load_prompt("target_anchor_extraction")
    assert "所有非空 `target_unit`" in load_prompt("target_aligned_segmentation")
    scoring = load_prompt("dimension_scoring")
    assert "不能新增错误" in scoring
    assert "correct=1" in scoring
    assert "本样本无适用项目" in scoring
    final = load_prompt("final_summary")
    assert "不得自行调整或重新计算" in final
