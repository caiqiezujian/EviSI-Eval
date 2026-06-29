# 数据契约

## 输入

源文：`sample_id`、`source_text` 必填；`reference_translation`、语言和领域可选。

系统译文：`sample_id`、`system_name`、`si_translation` 必填，组合键必须唯一。

## 无损约束

- `source_units[].source_unit` 按顺序拼接必须严格等于 `source_text`。
- `eval_units[].target_unit` 按顺序拼接必须严格等于 `si_translation`。
- 每个 `source_unit_id` 必须在全部 `eval_units[].source_unit_ids` 中出现一次且仅一次。
- 一个 eval unit 引用多个 source units 时，它们必须相邻且保持顺序。

## 证据约束

- Anchor/Event 的 `evidence_span` 必须逐字存在于所属 source/eval unit。
- Relation 使用 `evidence_spans` 数组，每个片段必须逐字存在于其引用的 units。
- `target_match` 非空时必须逐字存在于同传译文。
- 规范化字段不是逐字证据。

## ID

各阶段 ID 必须从 1 连续编号：`S`、`SA`、`SE`、`SR`、`E`、`TA`、`TE`、`TR`、`F`、`X`、`AJ`、`EJ`、`RJ`。

正式对象结构见 `schemas/source_card.schema.json`、`schemas/target_eval_card.schema.json` 和 `schemas/final_result.schema.json`。
