# 数据契约

## 1. 样本输入

每行一个 JSON 对象：

```json
{"sample_id":"s1","transcript":"source transcript","offline_translation":"optional reference","src_lang":"en","tgt_lang":"zh","domain":"medical"}
```

必填字段：`sample_id`、`transcript`。可选字段：`offline_translation`、`src_lang`、`tgt_lang`、`domain`。

## 2. 系统输出

```json
{"sample_id":"s1","system_name":"system_a","si_translation":"final SI translation"}
```

`(sample_id, system_name)` 必须唯一。当前评测不读取系统 ASR。

## 3. Source Card

Source Card 的主要数组为：

- `sentences`：源文逐字分句。
- `anchors`：出现级事实锚点。
- `events`：最小事件、参与者和边界属性。
- `relations`：事件之间的逻辑关系。
- `allowed_omissions`：填充语、假启动等允许省略内容。
- `metadata`：schema 版本、Prompt 哈希、模型、请求 ID 和 `card_hash`。

正式结构见 `schemas/source_card.schema.json`。

## 4. Target Analysis

在 Target Analysis 之前，`sentence_alignment` 保存：

- `target_units`：基于源文语义边界切分的逐字译文单元。
- `sentence_alignments`：每个源句恰好一条 1:1、1:N、N:1、omitted 或 uncertain 记录。
- `unaligned_target_unit_ids`：添加、填充或无法归属的译文单元。

正式结构见 `schemas/sentence_alignment.schema.json`。

- `target_units`：目标语义单元。
- `target_anchors`：译文锚点索引。
- `target_events`：译文事件索引。
- `target_relations`：译文实际表达的事件关系索引。

所有目标证据必须逐字存在于 `si_translation`。正式结构见 `schemas/target_analysis.schema.json`。

## 5. Evaluation Result

结果同时保留输入、源卡、目标分析、三类对齐、两类目标语言问题、复核、维度分数和最终分数。关键字段包括：

```text
source_card
sentence_alignment
target_analysis
anchor_alignments
event_alignments
relation_alignments
fluency_issues
efficiency_issues
dimension_scores
attributed_errors
review_queue
score_before_caps
final_score
```

正式结构见 `schemas/evaluation_result.schema.json`。

## 6. 证据规则

- `sentence_text`、`source_span`、`evidence_spans`、`source_cues` 必须逐字存在于源文。
- `unit_text`、`target_span`、`target_spans` 必须逐字存在于同传译文。
- `canonical_meaning`、`normalized_value` 可以规范化，但不能作为逐字证据。
- ID 在各自命名空间内唯一，所有引用必须指向已有项目。
