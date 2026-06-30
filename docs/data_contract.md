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

## 表达问题

```json
{"issue_id":"F1","issue_type":"grammar_fragment","target_span":"...","severity":"moderate","reason":"..."}
```

Severity 仅为 `minor|moderate|major|critical`。

## 最终结果

核心字段包括三类最终 judgements、两类 issues、`dimension_scores`、`dimension_weights`、`score_diagnostics`、`final_score`、`score_status`、`review` 和 `score_summary`。

当适用内容维度没有任何已决定项目时，该维度分数和 `final_score` 为 `null`，状态为 `provisional_no_decisions`。`score_diagnostics.<dimension>.decision_status` 可取 `not_applicable`、`no_decisions`、`partial_decisions` 或 `complete`。

机器可读 Schema 位于 `schemas/`。Python 运行时验证还额外执行跨字段和逐字证据约束。
