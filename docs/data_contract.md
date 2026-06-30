# EviSI-Eval v0.5 数据契约

所有输入和主要产物使用 UTF-8 JSONL，一行一个 JSON 对象。

## 输入样本

```json
{"sample_id":"s1","source_text":"...","reference_translation":null,"src_lang":"en","tgt_lang":"zh","domain":"general"}
```

- `sample_id`：非空且唯一。
- `source_text`：非空源语转录。
- `reference_translation`：可选，仅留档，不进入核心评测。

## 系统输出

```json
{"sample_id":"s1","system_name":"system_a","si_translation":"..."}
```

`(sample_id, system_name)` 必须唯一。

## Source Card

包含 `source_units`、`source_anchors`、`source_events`、`source_relations`。所有源项目都有 `importance: 1|2|3` 和逐字证据。卡片 metadata 包含 `source_card_hash` 与冻结标记。

Source 与 Target 的 Anchor/Event/Relation 必须共同遵守 `prompts/semantic_extraction_protocol.md`。两侧使用相同定义、类型边界和粒度，但独立、盲抽取：Source 不看译文，Target 不看原文。

## Eval Unit

```json
{"eval_unit_id":"E1","source_unit_ids":["S1"],"target_unit":"...","alignment_status":"aligned","reason":"..."}
```

状态仅为 `aligned|source_omitted|target_addition|uncertain`。所有 target units 拼接必须等于原译文；所有 source unit IDs 必须恰好覆盖一次。

## Judgement

```json
{
  "judgement_id":"AJ1",
  "source_anchor_id":"SA1",
  "source_evidence_spans":["..."],
  "eval_unit_ids":["E1"],
  "target_anchor_ids":["TA1"],
  "target_evidence_spans":["..."],
  "verdict":"correct",
  "confidence":0.95,
  "reason":"..."
}
```

Event 和 Relation 分别替换 source/target ID 字段。最终结果会增加 `review_verdict`、`review_confidence` 和 `resolution`。

Relation 的 `source_unit_ids` / `eval_unit_ids` 表示实际提供关系证据的单元，必须存在、唯一并按文本顺序排列，但允许非连续。远距离语篇关系不需要把无证据的中间单元加入 ID 数组。

每条 Relation 还必须满足：

- `related_source_event_ids` / `related_target_event_ids` 至少引用两个不同且真实存在的 Event；
- `relation_basis` 只能是 `explicit_cue` 或 `strong_semantic_entailment`；
- `explicit_cue` 必须提供位于证据单元中的逐字 `relation_cue`；
- `strong_semantic_entailment` 的 `relation_cue` 必须为空，且 `confidence >= 0.85`；
- 相邻、问答、同话题和文本先后本身不构成 Relation；没有合格关系时数组必须为空。

纯抽取产物使用 `schemas/target_semantic_card.schema.json`。旧卡缺少上述 Relation 依据字段，因此不会通过当前协议验证。

## 表达问题

```json
{"issue_id":"F1","issue_type":"grammar_fragment","target_span":"...","severity":"moderate","reason":"..."}
```

Severity 仅为 `minor|moderate|major|critical`。

## 最终结果

核心字段包括三类最终 judgements、两类 issues、`dimension_scores`、`dimension_weights`、`score_diagnostics`、`final_score`、`score_status`、`review` 和 `score_summary`。

当适用内容维度没有任何已决定项目时，该维度分数和 `final_score` 为 `null`，状态为 `provisional_no_decisions`。`score_diagnostics.<dimension>.decision_status` 可取 `not_applicable`、`no_decisions`、`partial_decisions` 或 `complete`。

机器可读 Schema 位于 `schemas/`。Python 运行时验证还额外执行跨字段和逐字证据约束。
