from pathlib import Path

from evisi_eval.prompt_loader import PROMPT_DIR, load_prompt


def test_source_anchor_prompt_preserves_domain_rules_and_structured_contract():
    prompt = load_prompt("source_anchors")
    required_rules = (
        "对象与指称实体",
        "数量、时间与度量",
        "术语与专业概念",
        "源文句子切分",
        "source_span",
        "normalized_value",
        "occurrence",
        "代词",
        "Round-robin um um load balancing scheme",
        "Failure Modes",
    )
    assert all(rule in prompt for rule in required_rules)
    assert "数量不能脱离指向对象机械抽取" in prompt
    assert '"anchor_id"' in prompt
    assert '"importance"' in prompt
    assert '"required"' in prompt


def test_source_event_prompt_preserves_event_scope_and_separates_relations():
    prompt = load_prompt("source_events")
    required_rules = (
        "动作事件",
        "变化事件",
        "状态与句内语义关系",
        "言说、认知与态度",
        "判断与评价",
        "条件、因果及其他事件间关系",
        "evidence_spans",
        "linked_anchor_ids",
        "polarity",
        "modality",
        "allowed_omissions",
        "Failure Modes",
    )
    assert all(rule in prompt for rule in required_rules)
    assert "不得额外生成第三个组合事件" in prompt
    assert "cause：head 是原因，dependent 是结果" in prompt


def test_target_prompt_uses_source_for_recall_but_requires_target_evidence():
    prompt = load_prompt("target_analysis")
    assert "不得把源文中存在、译文中缺失的信息复制" in prompt
    assert '"target_anchors"' in prompt
    assert '"target_events"' in prompt
    assert '"target_relations"' in prompt
    assert "不得根据常识、语法期待或可能的源文补全" in prompt


def test_sentence_alignment_prompt_handles_si_segmentation_without_forcing_one_to_one():
    prompt = load_prompt("sentence_alignment")
    assert "每个源句输出一条 alignment" in prompt
    assert "one_to_one" in prompt
    assert "one_to_many" in prompt
    assert "many_to_one" in prompt
    assert "翻错但可定位的片段已经对齐" in prompt
    assert "unaligned_target_unit_ids" in prompt


def test_no_draft_prompt_files_remain():
    assert not list(Path(PROMPT_DIR).glob("*draft*"))
