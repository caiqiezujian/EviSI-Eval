from evisi_eval.prompt_loader import PROMPT_FILES, load_prompt


def test_all_agent_prompts_and_repair_prompt_exist():
    """v0.4 has 3 agent prompts + 1 schema_repair prompt."""
    assert len(PROMPT_FILES) == 4
    expected = {"source_worker", "target_worker", "main_agent", "schema_repair"}
    assert set(PROMPT_FILES) == expected
    for name in PROMPT_FILES:
        prompt = load_prompt(name)
        assert prompt.strip()
        # Every prompt should reference JSON output format
        assert "JSON" in prompt or name == "schema_repair"


def test_source_worker_isolation():
    """SourceWorker never sees translations."""
    prompt = load_prompt("source_worker")
    assert "你只看源文" in prompt
    assert "看不到任何系统译文" in prompt


def test_target_worker_isolation():
    """TargetWorker never sees source analysis results."""
    prompt = load_prompt("target_worker")
    assert "你看不到源文的 anchor" in prompt
    assert "所有非空 `target_unit`" in prompt  # lossless segmentation


def test_main_agent_scoring_constraints():
    """MainAgent must not introduce new errors, uses structured evidence only."""
    prompt = load_prompt("main_agent")
    assert "不能新增错误" in prompt
    assert "correct=1" in prompt
    assert "本样本无适用项目" in prompt
    # Scoring must be based on structured evidence, no raw text re-reading
    assert "只能基于输入中的结构化数据" in prompt
    assert "看不到" in prompt  # no raw text access
