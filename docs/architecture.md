# 架构

## 设计边界

LLM 负责语义切分、抽取、对齐、判断、表达评价和维度评分。代码只负责输入隔离、调用编排、结构校验、逐字证据校验、无损拼接校验、固定权重计算、断点复用和报告。

## 三个对象

- `source_card`：一个源文样本共享一份，包含 source units、anchors、events、relations。
- `target_eval_card`：一个 `sample_id + system_name` 一份，包含 eval units、目标侧结构和表达问题。
- `final_result`：包含三类 judgement、全文复核、五维得分、固定加权总分和总结。

## 调用图

```text
source_text
  -> source units
  -> source anchors
  -> source events
  -> source relations
  -> source_card

source_card + one si_translation
  -> eval units
  -> target anchors / events / relations
  -> fluency / SI expression
  -> anchor / event / relation judgements
  -> global review
  -> five dimension scores
  -> fixed weighted score
  -> final summary
```

## 输入隔离

- 目标侧 Anchor/Event 抽取只看 `eval_unit_id + target_unit`，不看源文。
- Fluency 只看完整译文。
- Dimension Scoring 不看原文和译文，只看已有结构化判断。
- Reference Translation 不进入核心阶段。
- 实际系统名称不传给 LLM，产物落盘时由代码恢复。

## 失败策略

每个阶段先执行一次，结构不合格时最多执行两轮结构修复。源文切分失败时保留完整源文为一个 unit；译文对齐切分失败时保留完整双侧文本并标记 `uncertain`。其他语义抽取或评分阶段在修复仍失败时关闭该样本，避免用代码伪造语义结果。
