# EviSI-Eval Agent 需求与实施方案 v0.3

## 1. 项目定位

EviSI-Eval Agent 是一个面向同声传译最终译文的自动化质量评估 Agent。EviSI-Eval 是 Evidence-driven Simultaneous Interpretation Evaluation 的缩写，即“证据驱动的同声传译评估”。

本系统的目标是评价同传系统最终输出译文的质量。它不评价同传系统的实时过程，不评价 partial 输出，不评价真实延迟，不评价字幕稳定性，不评价音频质量，不评价系统 ASR，不评价语音播报效果。

系统输入包括一段源语转录文本、一个或多个同传系统的最终译文，以及可选真实译文或离线参考译文。系统输出每个同传系统在该样本上的五维分数、最终总分和可解释评估报告。

系统核心问题是：

听众通过某个同传系统的最终译文，是否获得了与源文一致、足够完整、清楚自然、符合同传表达特点的信息。

## 2. v0.3 的核心设计

v0.3 的核心设计是：

源文侧只构建一次，作为所有系统共享的评估基准。

每个系统译文单独进入译文评估链路。

源文不再和每个系统译文一起切分。源文只按句子或接近句子的自然句段进行无损切分，形成共享的 `source_units`。

每个系统译文不先做完全独立的 target units，而是在看到 `source_units` 后，直接进行“面向源文句子的对齐式切分”，输出 `eval_units`。每个 `eval_unit` 绑定一个或多个源文句子，并包含对应的译文片段。

因此，v0.3 的主流程是：

```text
A. 共享源文链路，只跑一次

1. 源文无损句子切分
2. 源文 anchor 抽取
3. 源文 event 抽取
4. 源文 relation 抽取


B. 单系统译文链路，每个系统跑一次

5. 译文对齐式无损切分
6. 译文 anchor 抽取
7. 译文 event 抽取
8. 译文 relation 抽取
9. 整体 fluency 评判
10. 整体 SI expression 评判


C. 内容判断与评分链路，每个系统跑一次

11. anchor 内容忠实度评判
12. event 内容忠实度评判
13. relation 内容忠实度评判
14. 内容忠实度全文复核
15. 五维分数计算
16. 总分计算与总结
```

这个版本解决了两个问题。

第一，多系统评测时，所有系统共享同一套源文切分、源文 anchor、源文 event 和源文 relation，评分基准统一。

第二，译文切分不是完全独立的自由切分，而是直接服务于源文句子级评估。它在 `source_units` 引导下生成 `eval_units`，后续所有译文 anchor、event、relation 都绑定到 `eval_unit_id`，避免“译文切分”和“内容评判范围”脱节。

## 3. 总体原则

本系统是大模型驱动的评估 Agent，不是硬编码规则评分器。

所有核心语义判断由大模型完成，包括源文切分、源文 anchor 抽取、源文 event 抽取、源文 relation 抽取、译文对齐式切分、译文 anchor 抽取、译文 event 抽取、译文 relation 抽取、内容忠实度判断、表达质量判断和维度评分。

代码层只负责流程编排、Prompt 调用、JSONL 读写、字段合并、断点续跑、格式校验、无损切分校验、日志记录和报告生成。代码不负责判断翻译是否正确，不负责用字符串规则判断 anchor、event 或 relation 是否匹配。

系统必须采用结构化链式流程，不能让大模型直接读取原文和译文后自由给总分。最终分数必须受前面结构化结果约束。

参考译文只能作为辅助信息，不能作为判错依据。v0.3 默认不将参考译文传入 anchor、event、relation、judgement 和 scoring 阶段。参考译文只可在必要时辅助理解源文大意、术语或边界，但不能替代源文，也不能用于判断同传译文是否正确。

## 4. 输入数据

系统输入分为两类：源文样本输入和系统译文输入。

### 4.1 源文样本输入

每条源文样本至少包含：

```json
{
  "sample_id": "sample_001",
  "source_text": "源语转录文本",
  "reference_translation": "可选真实译文或离线译文，可以为 null",
  "src_lang": "en",
  "tgt_lang": "zh",
  "domain": "可选领域"
}
```

其中 `source_text` 是唯一事实依据。

`reference_translation` 是辅助字段，不作为判错依据。当前 v0.3 中，核心抽取、判断和评分阶段默认不依赖该字段。

### 4.2 系统译文输入

每个系统译文至少包含：

```json
{
  "sample_id": "sample_001",
  "system_name": "system_a",
  "si_translation": "同传系统最终译文"
}
```

一个 `sample_id` 可以对应多个系统译文。每个系统译文独立评估，但共享同一个 `source_card`。

## 5. 核心输出

每个系统输出一份完整评估结果：

```json
{
  "sample_id": "sample_001",
  "system_name": "system_a",
  "dimension_scores": {
    "anchor_fidelity": 0,
    "event_fidelity": 0,
    "relation_fidelity": 0,
    "fluency": 0,
    "si_expression": 0
  },
  "dimension_weights": {
    "anchor_fidelity": 30,
    "event_fidelity": 25,
    "relation_fidelity": 20,
    "fluency": 15,
    "si_expression": 10
  },
  "final_score": 0,
  "score_summary": {
    "overall_judgement": "",
    "main_strengths": [],
    "main_errors": [],
    "uncertain_points": []
  }
}
```

除最终结果外，系统必须保存完整中间结果，包括：

```text
source_units
source_anchors
source_events
source_relations

eval_units
target_anchors
target_events
target_relations
fluency_issues
si_expression_issues

anchor_judgements
event_judgements
relation_judgements
global_fidelity_review

dimension_scores
final_score
score_summary
```

## 6. 核心数据对象

v0.3 中有三个核心数据对象。

```text
source_card：共享源文卡片
target_eval_card：某个系统译文的评估卡片
final_result：某个系统的最终评分结果
```

### 6.1 source_card

`source_card` 是源文共享底稿。一个 `sample_id` 只生成一份。

```json
{
  "sample_id": "sample_001",
  "source_text": "...",
  "src_lang": "en",
  "tgt_lang": "zh",
  "domain": "optional",

  "source_units": [
    {
      "source_unit_id": "S1",
      "source_unit": "源文中的一个完整句子或自然句段"
    }
  ],

  "source_anchors": [
    {
      "source_unit_id": "S1",
      "source_anchor_id": "SA1",
      "anchor_text": "anchor surface text",
      "normalized_meaning": "normalized meaning",
      "evidence_span": "verbatim source evidence span"
    }
  ],

  "source_events": [
    {
      "source_unit_id": "S1",
      "source_event_id": "SE1",
      "event_text": "event surface text or concise description",
      "canonical_meaning": "canonical event meaning",
      "evidence_span": "verbatim source evidence span"
    }
  ],

  "source_relations": [
    {
      "source_relation_id": "SR1",
      "source_unit_ids": ["S1", "S2"],
      "relation_text": "relation description",
      "relation_meaning": "canonical relation meaning",
      "evidence_span": "verbatim source evidence span",
      "related_source_event_ids": ["SE1", "SE2"]
    }
  ]
}
```

### 6.2 target_eval_card

`target_eval_card` 是某个系统译文在共享源文底稿下生成的评估卡片。一个 `sample_id + system_name` 生成一份。

```json
{
  "sample_id": "sample_001",
  "system_name": "system_a",
  "si_translation": "...",

  "eval_units": [
    {
      "eval_unit_id": "E1",
      "source_unit_ids": ["S1"],
      "target_unit": "译文中的对应片段",
      "alignment_status": "aligned | source_omitted | target_addition | uncertain",
      "reason": "brief reason"
    }
  ],

  "target_anchors": [
    {
      "eval_unit_id": "E1",
      "target_anchor_id": "TA1",
      "anchor_text": "anchor surface text",
      "normalized_meaning": "normalized meaning",
      "evidence_span": "verbatim target evidence span"
    }
  ],

  "target_events": [
    {
      "eval_unit_id": "E1",
      "target_event_id": "TE1",
      "event_text": "event surface text or concise description",
      "canonical_meaning": "canonical event meaning",
      "evidence_span": "verbatim target evidence span"
    }
  ],

  "target_relations": [
    {
      "target_relation_id": "TR1",
      "eval_unit_ids": ["E1", "E2"],
      "relation_text": "relation description",
      "relation_meaning": "canonical relation meaning",
      "evidence_span": "verbatim target evidence span",
      "related_target_event_ids": ["TE1", "TE2"]
    }
  ],

  "fluency_issues": [],
  "fluency_assessment": "",

  "si_expression_issues": [],
  "si_expression_assessment": ""
}
```

### 6.3 final_result

`final_result` 是某个系统的完整评估结果。

```json
{
  "sample_id": "sample_001",
  "system_name": "system_a",

  "anchor_judgements": [],
  "event_judgements": [],
  "relation_judgements": [],

  "global_fidelity_review": {},

  "dimension_scores": {
    "anchor_fidelity": 0,
    "event_fidelity": 0,
    "relation_fidelity": 0,
    "fluency": 0,
    "si_expression": 0
  },

  "dimension_score_explanations": {
    "anchor_fidelity": "",
    "event_fidelity": "",
    "relation_fidelity": "",
    "fluency": "",
    "si_expression": ""
  },

  "dimension_weights": {
    "anchor_fidelity": 30,
    "event_fidelity": 25,
    "relation_fidelity": 20,
    "fluency": 15,
    "si_expression": 10
  },

  "final_score": 0,

  "score_summary": {
    "overall_judgement": "",
    "main_strengths": [],
    "main_errors": [],
    "uncertain_points": []
  }
}
```

## 7. 评分维度与权重

最终评分采用五个维度，总分 100 分。

```text
anchor_fidelity：30
event_fidelity：25
relation_fidelity：20
fluency：15
si_expression：10
```

### 7.1 Anchor Fidelity，30 分

Anchor Fidelity 评估源文中的关键 anchor 是否在同传译文中被准确传达。

Anchor 是关键可核验信息锚点，不等于传统 NER 实体。它包括人名、机构、地点、时间、数字、数量、金额、比例、百分比、单位、项目名、政策名、文件名、专业术语、限定对象、明确指称的群体或范围。

Anchor 不负责动作、变化方向、判断、态度、否定、情态和逻辑关系。

### 7.2 Event Fidelity，25 分

Event Fidelity 评估源文中的核心事件语义是否被同传译文准确保留。

Event 关注“谁做了什么”“什么发生了变化”“谁对谁产生影响”“某人表达了什么判断或态度”“某状态是否成立”等语义结构。

Event 包括主体、动作、状态、变化方向、判断、态度、否定、情态、主客体关系、施事受事关系和范围边界等。

### 7.3 Relation Fidelity，20 分

Relation Fidelity 评估源文中的逻辑关系是否被同传译文准确保留。

Relation 关注事件之间、命题之间或信息片段之间的逻辑关系，包括因果、条件、转折、让步、目的、时序、比较、归因、解释、例外、递进等。

### 7.4 Fluency，15 分

Fluency 评估完整同传译文本身是否清楚、自然、可理解。

Fluency 只看完整 `si_translation`，不按 eval unit 逐句评估，也不看源文。它只判断目标语整体清楚度、自然度和可理解性。

内容误译、漏译、逻辑错误不属于 fluency 问题，除非它们同时造成目标语文本本身不可理解。

### 7.5 SI Expression，10 分

SI Expression 评估完整同传译文是否符合同传表达要求。

它可以看完整 `source_text` 和完整 `si_translation`，但不负责判断 anchor、event、relation 是否忠实。它主要判断译文作为同传输出是否简洁、顺畅、有效，是否存在无意义重复、过度填充、拖沓、反复改述、无必要解释、明显不必要添加等问题。

## 8. 文件组织与执行方式

v0.3 建议按三类 JSONL 文件组织。

### 8.1 源文侧文件

源文侧只运行一次。

```text
source_00_input.jsonl
source_01_units.jsonl
source_02_anchors.jsonl
source_03_events.jsonl
source_04_relations.jsonl
source_cards.jsonl
```

`source_cards.jsonl` 是最终共享源文底稿。

### 8.2 单系统译文侧文件

每个系统译文都运行一次。

```text
target_00_input.jsonl
target_01_eval_units.jsonl
target_02_anchors.jsonl
target_03_events.jsonl
target_04_relations.jsonl
target_05_fluency.jsonl
target_06_si_expression.jsonl
target_eval_cards.jsonl
```

`target_eval_cards.jsonl` 是当前系统译文的评估卡片。

### 8.3 评分侧文件

每个系统译文都运行一次。

```text
score_01_anchor_judgements.jsonl
score_02_event_judgements.jsonl
score_03_relation_judgements.jsonl
score_04_global_review.jsonl
score_05_dimension_scores.jsonl
score_06_final_results.jsonl
```

`score_06_final_results.jsonl` 是最终评分结果。

## 9. Step 1：源文无损句子切分

### 9.1 目标

只读取 `source_text`，将源文无损切分为 `source_units`。

本步骤不看任何系统译文，不做源译对齐，不抽 anchor，不抽 event，不抽 relation，不判断翻译质量。

### 9.2 输入

```json
{
  "sample_id": "sample_001",
  "source_text": "...",
  "src_lang": "en",
  "tgt_lang": "zh",
  "domain": "optional"
}
```

### 9.3 输出

```json
{
  "sample_id": "sample_001",
  "source_units": [
    {
      "source_unit_id": "S1",
      "source_unit": "verbatim source sentence or natural segment"
    }
  ]
}
```

### 9.4 关键要求

源文切分的基本粒度是句子或接近句子的自然句段。

不要做句内细切分。句子内部的定语从句、倒装结构、插入语、后置修饰、长宾语、状语、补语等不拆开。

切分必须无损。所有 `source_unit` 按顺序拼接后，必须等于输入的 `source_text`。

必须保留原始标点、空格、换行、口语填充、重复、残句和异常文本。

### 9.5 下一步对接

本步骤输出的 `source_units` 将作为 Step 2、Step 3、Step 4 和 Step 5 的输入。

Step 2 使用 `source_units` 抽取 `source_anchors`。

Step 3 使用 `source_units` 抽取 `source_events`。

Step 4 使用 `source_units + source_events` 抽取 `source_relations`。

Step 5 使用 `source_units + si_translation` 生成 `eval_units`。

## 10. Step 2：源文 Anchor 抽取

### 10.1 目标

只读取 `source_units`，抽取源文中的关键可核验信息锚点，输出 `source_anchors`。

本步骤不看任何译文，不做源译比较，不判断翻译是否正确。

### 10.2 输入

```json
{
  "sample_id": "sample_001",
  "source_units": [
    {
      "source_unit_id": "S1",
      "source_unit": "..."
    }
  ]
}
```

### 10.3 输出

```json
{
  "source_anchors": [
    {
      "source_unit_id": "S1",
      "source_anchor_id": "SA1",
      "anchor_text": "anchor surface text",
      "normalized_meaning": "normalized meaning",
      "evidence_span": "verbatim source evidence span"
    }
  ]
}
```

### 10.4 关键要求

每个 anchor 必须绑定一个合法的 `source_unit_id`。

`source_anchor_id` 按 SA1、SA2、SA3 顺序编号，不得重复。

`evidence_span` 必须是对应 `source_unit` 中逐字出现的连续片段。

`normalized_meaning` 可以轻度标准化，但不能加入源文没有的信息。

本步骤不输出 anchor 类型，不输出重要程度，不输出 judgement，不输出 score。

### 10.5 下一步对接

本步骤输出的 `source_anchors` 将作为 Step 11 的输入，用于 anchor 内容忠实度评判。

## 11. Step 3：源文 Event 抽取

### 11.1 目标

只读取 `source_units`，抽取源文中的最小完整事件、状态或判断，输出 `source_events`。

本步骤不看译文，不看 source anchors，不做比较，不打分。

### 11.2 输入

```json
{
  "sample_id": "sample_001",
  "source_units": [
    {
      "source_unit_id": "S1",
      "source_unit": "..."
    }
  ]
}
```

### 11.3 输出

```json
{
  "source_events": [
    {
      "source_unit_id": "S1",
      "source_event_id": "SE1",
      "event_text": "event surface text or concise description",
      "canonical_meaning": "canonical event meaning",
      "evidence_span": "verbatim source evidence span"
    }
  ]
}
```

### 11.4 关键要求

Event 是文本中表达的最小完整语义事件、状态或判断。

Event 应尽量表达完整语义，不要只抽孤立动词或孤立名词。

每个 event 必须绑定一个合法的 `source_unit_id`。

`source_event_id` 按 SE1、SE2、SE3 顺序编号，不得重复。

`evidence_span` 必须是对应 `source_unit` 中逐字出现的连续片段。

本步骤不使用 source anchor 结果，不判断译文质量，不打分。

### 11.5 下一步对接

本步骤输出的 `source_events` 将作为 Step 4 和 Step 12 的输入。

Step 4 使用 `source_events` 抽取源文 relation。

Step 12 使用 `source_events` 与 `target_events` 进行 event 内容忠实度评判。

## 12. Step 4：源文 Relation 抽取

### 12.1 目标

读取 `source_units` 和 `source_events`，抽取源文中的逻辑关系，输出 `source_relations`。

Relation 可以参考同一侧的 events，因为 relation 是事件或命题之间的逻辑连接。

### 12.2 输入

```json
{
  "sample_id": "sample_001",
  "source_units": [
    {
      "source_unit_id": "S1",
      "source_unit": "..."
    }
  ],
  "source_events": [
    {
      "source_unit_id": "S1",
      "source_event_id": "SE1",
      "event_text": "...",
      "canonical_meaning": "...",
      "evidence_span": "..."
    }
  ]
}
```

### 12.3 输出

```json
{
  "source_relations": [
    {
      "source_relation_id": "SR1",
      "source_unit_ids": ["S1", "S2"],
      "relation_text": "relation description",
      "relation_meaning": "canonical relation meaning",
      "evidence_span": "verbatim source evidence span",
      "related_source_event_ids": ["SE1", "SE2"]
    }
  ]
}
```

### 12.4 关键要求

Relation 是事件之间、命题之间或信息片段之间的逻辑关系。

Relation 可以在同一个 source unit 内，也可以跨相邻 source units。

每个 relation 必须绑定 `source_unit_ids`。

`source_relation_id` 按 SR1、SR2、SR3 顺序编号，不得重复。

`related_source_event_ids` 必须来自已有 `source_events`。如果无法稳定绑定 event，可以为空数组，但不能编造 event_id。

`evidence_span` 必须能在对应 source units 中找到逐字证据。

### 12.5 下一步对接

本步骤输出的 `source_relations` 将作为 Step 13 的输入，用于 relation 内容忠实度评判。

到 Step 4 结束后，可以形成完整共享 `source_card`。

## 13. Step 5：译文对齐式无损切分

### 13.1 目标

读取共享 `source_units` 和当前系统的完整 `si_translation`，生成 `eval_units`。

本步骤同时完成两件事：

第一，将当前系统译文无损切分为若干 `target_unit`。

第二，将每个 `target_unit` 对齐到一个或多个 `source_unit_id`，形成后续内容忠实度评判的局部比较范围。

本步骤不抽 anchor，不抽 event，不抽 relation，不判断译文内容是否正确，不打分。

### 13.2 输入

```json
{
  "sample_id": "sample_001",
  "system_name": "system_a",
  "si_translation": "...",
  "source_units": [
    {
      "source_unit_id": "S1",
      "source_unit": "..."
    }
  ]
}
```

### 13.3 输出

```json
{
  "eval_units": [
    {
      "eval_unit_id": "E1",
      "source_unit_ids": ["S1"],
      "target_unit": "verbatim target segment",
      "alignment_status": "aligned | source_omitted | target_addition | uncertain",
      "reason": "brief reason"
    }
  ]
}
```

### 13.4 关键要求

译文切分必须无损。所有非空 `target_unit` 按输出顺序拼接后，必须等于输入的 `si_translation`。

每个 `source_unit_id` 必须在 `eval_units` 的 `source_unit_ids` 中出现一次且仅出现一次。即使某个源文句子没有对应译文，也必须通过 `source_omitted` 记录。

`source_unit_ids` 可以为空数组，此时表示 `target_addition`。

`target_unit` 可以为空字符串，此时表示 `source_omitted`。

`source_unit_ids` 中的源文句子应是相邻、连续的源文句子，不能把相距很远的源文句子强行合并到一个 eval unit。

如果源文 A、B 在译文中表现为 B′、A′，应将 S1 和 S2 合并进同一个 eval unit，`target_unit` 为 B′+A′。不要强行输出 A 对 B′、B 对 A′。

翻错仍然对齐。只要译文片段明显是在尝试表达某个源文片段，即使内容错误，也应标为 `aligned`。

如果某个源文句子没有任何实质对应译文，则输出 `source_omitted`，`target_unit` 为空字符串。

如果译文中存在无源文依据的独立片段，则输出 `target_addition`，`source_unit_ids` 为空数组。

如果无依据添加嵌入在一个译文句子内部，不要强行句内切开；保留在对应 `target_unit` 中，后续由 SI expression 或全文复核处理。

### 13.5 alignment_status 定义

`aligned`：该译文片段与一个或多个源文句子存在明确或基本明确的对应关系。

`source_omitted`：一个或多个源文句子在译文中没有任何实质对应表达。

`target_addition`：译文片段没有对应源文依据。

`uncertain`：存在可能对应关系，但边界、归属或顺序关系不稳定，无法可靠判断。

### 13.6 下一步对接

本步骤输出的 `eval_units` 将作为 Step 6、Step 7、Step 8、Step 11、Step 12、Step 13 和 Step 14 的输入。

Step 6 基于 `eval_units.target_unit` 抽取 `target_anchors`。

Step 7 基于 `eval_units.target_unit` 抽取 `target_events`。

Step 8 基于 `eval_units.target_unit + target_events` 抽取 `target_relations`。

Step 11、12、13 基于 `eval_units` 将源文结构和译文结构放入同一局部比较范围。

## 14. Step 6：译文 Anchor 抽取

### 14.1 目标

只读取 `eval_units` 中的 `target_unit`，抽取译文中实际出现的 anchor，输出 `target_anchors`。

本步骤不看 source_units，不看 source_anchors，不判断译文中的 anchor 是否正确。

即使译文中的 anchor 是错误翻译，也必须如实抽取。

### 14.2 输入

```json
{
  "sample_id": "sample_001",
  "system_name": "system_a",
  "eval_units": [
    {
      "eval_unit_id": "E1",
      "target_unit": "..."
    }
  ]
}
```

实际传入模型时，建议只传 `eval_unit_id` 和 `target_unit`，不要传 `source_unit_ids` 和源文内容，避免模型根据源文脑补译文 anchor。

### 14.3 输出

```json
{
  "target_anchors": [
    {
      "eval_unit_id": "E1",
      "target_anchor_id": "TA1",
      "anchor_text": "anchor surface text",
      "normalized_meaning": "normalized meaning",
      "evidence_span": "verbatim target evidence span"
    }
  ]
}
```

### 14.4 关键要求

每个 target anchor 必须绑定一个合法的 `eval_unit_id`。

`target_anchor_id` 按 TA1、TA2、TA3 顺序编号，不得重复。

`evidence_span` 必须是对应 `target_unit` 中逐字出现的连续片段。

本步骤不输出 anchor 类型，不输出重要程度，不输出 judgement，不输出 score。

### 14.5 下一步对接

本步骤输出的 `target_anchors` 将作为 Step 11 的输入，用于 anchor 内容忠实度评判。

## 15. Step 7：译文 Event 抽取

### 15.1 目标

只读取 `eval_units` 中的 `target_unit`，抽取译文实际表达的 event，输出 `target_events`。

本步骤不看源文，不看 target anchors，不判断译文是否正确。

### 15.2 输入

```json
{
  "sample_id": "sample_001",
  "system_name": "system_a",
  "eval_units": [
    {
      "eval_unit_id": "E1",
      "target_unit": "..."
    }
  ]
}
```

实际传入模型时，建议只传 `eval_unit_id` 和 `target_unit`。

### 15.3 输出

```json
{
  "target_events": [
    {
      "eval_unit_id": "E1",
      "target_event_id": "TE1",
      "event_text": "event surface text or concise description",
      "canonical_meaning": "canonical event meaning",
      "evidence_span": "verbatim target evidence span"
    }
  ]
}
```

### 15.4 关键要求

每个 target event 必须绑定一个合法的 `eval_unit_id`。

`target_event_id` 按 TE1、TE2、TE3 顺序编号，不得重复。

`evidence_span` 必须是对应 `target_unit` 中逐字出现的连续片段。

本步骤不使用 target anchor 结果，不看源文，不做内容忠实度判断。

### 15.5 下一步对接

本步骤输出的 `target_events` 将作为 Step 8 和 Step 12 的输入。

Step 8 使用 `target_events` 抽取译文 relation。

Step 12 使用 `target_events` 与 `source_events` 进行 event 内容忠实度评判。

## 16. Step 8：译文 Relation 抽取

### 16.1 目标

读取 `eval_units.target_unit` 和 `target_events`，抽取译文中的逻辑关系，输出 `target_relations`。

本步骤不看源文，不判断译文关系是否忠实。

### 16.2 输入

```json
{
  "sample_id": "sample_001",
  "system_name": "system_a",
  "eval_units": [
    {
      "eval_unit_id": "E1",
      "target_unit": "..."
    }
  ],
  "target_events": [
    {
      "eval_unit_id": "E1",
      "target_event_id": "TE1",
      "event_text": "...",
      "canonical_meaning": "...",
      "evidence_span": "..."
    }
  ]
}
```

实际传入模型时，不传源文内容和源文结构。

### 16.3 输出

```json
{
  "target_relations": [
    {
      "target_relation_id": "TR1",
      "eval_unit_ids": ["E1", "E2"],
      "relation_text": "relation description",
      "relation_meaning": "canonical relation meaning",
      "evidence_span": "verbatim target evidence span",
      "related_target_event_ids": ["TE1", "TE2"]
    }
  ]
}
```

### 16.4 关键要求

Relation 可以在同一个 eval unit 内，也可以跨相邻 eval units。

每个 relation 必须绑定 `eval_unit_ids`。

`target_relation_id` 按 TR1、TR2、TR3 顺序编号，不得重复。

`related_target_event_ids` 必须来自已有 `target_events`。如果无法稳定绑定 event，可以为空数组，但不能编造 event_id。

`evidence_span` 必须能在对应 eval units 的 target_unit 中找到逐字证据。

### 16.5 下一步对接

本步骤输出的 `target_relations` 将作为 Step 13 的输入，用于 relation 内容忠实度评判。

## 17. Step 9：整体 Fluency 评判

### 17.1 目标

只读取完整 `si_translation`，评估译文本身是否清楚、自然、可理解。

本步骤不看源文，不判断译文是否忠实。内容误译、漏译、逻辑错误不属于 fluency 问题，除非它们同时导致目标语文本本身不可理解。

### 17.2 输入

```json
{
  "sample_id": "sample_001",
  "system_name": "system_a",
  "si_translation": "完整同传译文"
}
```

### 17.3 输出

```json
{
  "fluency_issues": [
    {
      "issue_id": "F1",
      "target_span": "verbatim target span",
      "issue_description": "brief issue description",
      "severity": "minor | moderate | major | critical"
    }
  ],
  "fluency_assessment": "overall fluency assessment"
}
```

### 17.4 关键要求

Fluency 是整体译文维度，不按 eval unit 逐句评估。

每个 fluency issue 必须引用完整 `si_translation` 中逐字出现的 `target_span`。

不要因为译文口语化、顺句驱动、简短或不同于参考译文就判为 fluency 问题。

不要把内容忠实度错误重复记为 fluency 问题。

### 17.5 下一步对接

本步骤输出的 `fluency_issues` 和 `fluency_assessment` 将作为 Step 15 和 Step 16 的输入。

## 18. Step 10：整体 SI Expression 评判

### 18.1 目标

读取完整 `source_text` 和完整 `si_translation`，评估译文作为同传输出是否简洁、顺畅、有效。

SI Expression 不负责判断 anchor、event、relation 是否忠实。它主要判断同传表达形态。

### 18.2 输入

```json
{
  "sample_id": "sample_001",
  "system_name": "system_a",
  "source_text": "完整源文",
  "si_translation": "完整同传译文"
}
```

### 18.3 输出

```json
{
  "si_expression_issues": [
    {
      "issue_id": "X1",
      "target_span": "verbatim target span",
      "issue_description": "brief issue description",
      "severity": "minor | moderate | major | critical"
    }
  ],
  "si_expression_assessment": "overall SI expression assessment"
}
```

### 18.4 关键要求

需要识别无意义重复、过度填充、拖沓、反复改述、无必要解释、明显不必要添加、顺句堆叠导致听众理解负担过高等问题。

不要惩罚合理压缩。

不要惩罚合理省略低信息量口语内容。

不要因为译文不同于参考译文就判为问题。

不要把 anchor、event、relation 的内容误译重复记为 SI expression 问题。

明显无依据添加可以作为 SI expression 问题记录。如果无依据添加造成严重事实误导，也应在 Step 14 的全文复核中记录。

### 18.5 下一步对接

本步骤输出的 `si_expression_issues` 和 `si_expression_assessment` 将作为 Step 14、Step 15 和 Step 16 的输入。

## 19. Step 11：Anchor 内容忠实度评判

### 19.1 目标

读取 `source_anchors`、`target_anchors` 和 `eval_units`，判断每个源文 anchor 是否在当前系统译文中被准确传达。

### 19.2 输入

```json
{
  "sample_id": "sample_001",
  "system_name": "system_a",
  "source_units": [],
  "eval_units": [],
  "source_anchors": [],
  "target_anchors": []
}
```

本步骤需要知道 `eval_units.source_unit_ids`，从而将源文 anchor 映射到对应的 eval unit 中。

### 19.3 输出

```json
{
  "anchor_judgements": [
    {
      "anchor_judgement_id": "AJ1",
      "eval_unit_id": "E1",
      "source_anchor_id": "SA1",
      "source_anchor": "source anchor text",
      "target_match": "target expression or empty string",
      "target_anchor_ids": ["TA1"],
      "verdict": "correct | partially_correct | incorrect | missing | uncertain",
      "explanation": "brief explanation"
    }
  ],
  "anchor_fidelity_assessment": "overall anchor fidelity assessment"
}
```

### 19.4 判断原则

必须为每个 `source_anchor` 输出一条 judgement。

默认在该 source anchor 所属 source unit 对应的 eval unit 内寻找 target anchor。

如果存在明显同传延迟、局部倒序或句组合并，可以在相邻 eval unit 中寻找对应，但必须在 explanation 中说明。

判断语义等价，不做字符串匹配。一个中文 anchor 可能对应多个英文表达，一个英文 anchor 也可能对应多个中文表达。不能因为译文没有采用某个固定标准译法就判错。

如果译文准确表达源文 anchor，verdict = correct。

如果译文表达了部分信息但不完整，verdict = partially_correct。

如果译文表达了错误的对象、数字、时间、术语、范围或单位，verdict = incorrect。

如果找不到任何对应表达，verdict = missing。

如果证据不足或存在多种合理解释，verdict = uncertain。

### 19.5 下一步对接

本步骤输出的 `anchor_judgements` 和 `anchor_fidelity_assessment` 将作为 Step 14 和 Step 15 的输入。

## 20. Step 12：Event 内容忠实度评判

### 20.1 目标

读取 `source_events`、`target_events` 和 `eval_units`，判断每个源文 event 是否在当前系统译文中被准确保留。

### 20.2 输入

```json
{
  "sample_id": "sample_001",
  "system_name": "system_a",
  "source_units": [],
  "eval_units": [],
  "source_events": [],
  "target_events": []
}
```

### 20.3 输出

```json
{
  "event_judgements": [
    {
      "event_judgement_id": "EJ1",
      "eval_unit_id": "E1",
      "source_event_id": "SE1",
      "source_event": "source event",
      "target_match": "target event expression or empty string",
      "target_event_ids": ["TE1"],
      "verdict": "correct | partially_correct | incorrect | missing | uncertain",
      "explanation": "brief explanation"
    }
  ],
  "event_fidelity_assessment": "overall event fidelity assessment"
}
```

### 20.4 判断原则

必须为每个 `source_event` 输出一条 judgement。

默认在该 source event 所属 source unit 对应的 eval unit 内寻找 target event。

如果存在明显同传延迟、局部倒序或句组合并，可以在相邻 eval unit 中寻找对应，但必须说明原因。

判断事件语义是否保留，而不是判断表面词是否一致。

如果主体、动作、状态、变化方向、判断、态度、否定、情态、主客体关系等核心含义准确保留，verdict = correct。

如果事件大体保留但存在局部信息损失，verdict = partially_correct。

如果事件方向、主体、对象、否定、情态、判断或核心动作错误，verdict = incorrect。

如果源文 event 没有对应表达，verdict = missing。

如果证据不足或存在多种合理解释，verdict = uncertain。

不要重复判断 anchor 错误，除非 anchor 错误导致事件语义本身发生变化。

### 20.5 下一步对接

本步骤输出的 `event_judgements` 和 `event_fidelity_assessment` 将作为 Step 14 和 Step 15 的输入。

## 21. Step 13：Relation 内容忠实度评判

### 21.1 目标

读取 `source_relations`、`target_relations`、`source_events`、`target_events` 和 `eval_units`，判断源文逻辑关系是否在当前系统译文中被准确保留。

### 21.2 输入

```json
{
  "sample_id": "sample_001",
  "system_name": "system_a",
  "eval_units": [],
  "source_relations": [],
  "target_relations": [],
  "source_events": [],
  "target_events": []
}
```

### 21.3 输出

```json
{
  "relation_judgements": [
    {
      "relation_judgement_id": "RJ1",
      "source_relation_id": "SR1",
      "source_relation": "source relation",
      "target_match": "target relation expression or empty string",
      "target_relation_ids": ["TR1"],
      "verdict": "correct | weakened | incorrect | missing | uncertain",
      "explanation": "brief explanation"
    }
  ],
  "relation_fidelity_assessment": "overall relation fidelity assessment"
}
```

### 21.4 判断原则

必须为每个 `source_relation` 输出一条 judgement。

判断关系是否保留，而不是判断关系词是否字面一致。

如果逻辑关系准确保留，verdict = correct。

如果关系被弱化但仍能大体理解，verdict = weakened。

如果关系被反转、误置或变成另一种关系，verdict = incorrect。

如果源文关系没有对应表达，verdict = missing。

如果证据不足，verdict = uncertain。

不要重复判断 anchor 或 event 错误，除非 relation 本身发生独立错误。

### 21.5 下一步对接

本步骤输出的 `relation_judgements` 和 `relation_fidelity_assessment` 将作为 Step 14 和 Step 15 的输入。

## 22. Step 14：内容忠实度全文复核

### 22.1 目标

全文复核在 anchor、event、relation judgement 完成之后进行。它不重新自由打分，而是检查局部判断是否存在遗漏、冲突、重复或需要解释的全文现象。

内容忠实度采用“eval unit 为主，全文复核为辅”的原则。

### 22.2 输入

```json
{
  "sample_id": "sample_001",
  "system_name": "system_a",
  "source_text": "...",
  "si_translation": "...",
  "source_units": [],
  "eval_units": [],
  "anchor_judgements": [],
  "event_judgements": [],
  "relation_judgements": [],
  "si_expression_issues": []
}
```

### 22.3 输出

```json
{
  "global_fidelity_review": {
    "delayed_expression_notes": [],
    "consistency_notes": [],
    "possible_duplicate_errors": [],
    "missed_global_issues": [],
    "misleading_addition_notes": [],
    "overall_fidelity_comment": ""
  }
}
```

### 22.4 复核重点

检查某个 source anchor、event 或 relation 是否在当前 eval unit 中看似缺失，但在相邻 eval unit 或后文中被明确延迟表达。

检查术语、对象、指代在全文中是否一致。

检查同一个错误是否被多个 judgement 重复记录。

检查是否存在跨句逻辑关系漏判。

检查译文整体是否造成源文没有的严重误导。

检查 target_addition 或 SI expression 中的无依据添加是否造成事实误导。

### 22.5 下一步对接

本步骤输出的 `global_fidelity_review` 将作为 Step 15 和 Step 16 的输入。

## 23. Step 15：五维分数计算

### 23.1 目标

根据已经生成的结构化结果，为五个维度分别给出 0 到 100 分。

本步骤不能新增错误。它只能使用前面已经生成的 judgement、issue 和 review。

### 23.2 输入

```json
{
  "sample_id": "sample_001",
  "system_name": "system_a",
  "anchor_judgements": [],
  "event_judgements": [],
  "relation_judgements": [],
  "fluency_issues": [],
  "fluency_assessment": "",
  "si_expression_issues": [],
  "si_expression_assessment": "",
  "global_fidelity_review": {}
}
```

### 23.3 输出

```json
{
  "dimension_scores": {
    "anchor_fidelity": 0,
    "event_fidelity": 0,
    "relation_fidelity": 0,
    "fluency": 0,
    "si_expression": 0
  },
  "dimension_score_explanations": {
    "anchor_fidelity": "",
    "event_fidelity": "",
    "relation_fidelity": "",
    "fluency": "",
    "si_expression": ""
  }
}
```

### 23.4 评分尺度

五个维度统一采用 0 到 100 分。

```text
95-100：几乎没有实质问题，只有极轻微瑕疵。
85-94：整体很好，存在少量局部问题，但不影响主要信息理解。
75-84：基本可用，有若干明显问题，但核心内容大体保留。
60-74：问题较多，听众能理解部分主要内容，但信息损失或误导明显。
40-59：严重不完整或多处误译，只能保留少量有效信息。
0-39：整体失败，大量核心信息缺失、反译或不可理解。
```

### 23.5 关键要求

本步骤不能读取原文和译文后重新自由判错。

本步骤不能新增错误。

如果评分器发现疑似新问题，只能写入解释中的“需要复核”内容，不能直接用于扣分。

每个维度分数必须和对应的 judgement 或 issue 一致。

### 23.6 下一步对接

本步骤输出的 `dimension_scores` 和 `dimension_score_explanations` 将作为 Step 16 的输入。

## 24. Step 16：总分计算与总结

### 24.1 目标

根据五个维度分数和固定权重计算最终总分，并生成最终总结。

### 24.2 输入

```json
{
  "sample_id": "sample_001",
  "system_name": "system_a",
  "dimension_scores": {
    "anchor_fidelity": 0,
    "event_fidelity": 0,
    "relation_fidelity": 0,
    "fluency": 0,
    "si_expression": 0
  },
  "dimension_score_explanations": {},
  "anchor_judgements": [],
  "event_judgements": [],
  "relation_judgements": [],
  "fluency_issues": [],
  "si_expression_issues": [],
  "global_fidelity_review": {}
}
```

### 24.3 总分公式

总分采用固定权重：

```text
anchor_fidelity：30
event_fidelity：25
relation_fidelity：20
fluency：15
si_expression：10
```

最终分数计算公式：

```text
final_score =
anchor_fidelity × 0.30
+ event_fidelity × 0.25
+ relation_fidelity × 0.20
+ fluency × 0.15
+ si_expression × 0.10
```

五个维度分数由大模型根据结构化证据生成。最终加权汇总可以由程序机械计算。程序只执行评价协议，不进行语义判断。

### 24.4 输出

```json
{
  "dimension_weights": {
    "anchor_fidelity": 30,
    "event_fidelity": 25,
    "relation_fidelity": 20,
    "fluency": 15,
    "si_expression": 10
  },
  "final_score": 0,
  "score_summary": {
    "overall_judgement": "",
    "main_strengths": [],
    "main_errors": [],
    "uncertain_points": []
  }
}
```

### 24.5 关键要求

最终总结必须基于前面已经生成的结构化结果。

不能新增错误。

不能重新自由评价。

总结需要说明主要优势、主要问题、不确定点和最终分数原因。

## 25. Prompt 模板规划

v0.3 推荐使用以下 Prompt 模板。

```text
1. source_sentence_segmentation_prompt

2. source_anchor_extraction_prompt
3. source_event_extraction_prompt
4. source_relation_extraction_prompt

5. target_aligned_segmentation_prompt
6. target_anchor_extraction_prompt
7. target_event_extraction_prompt
8. target_relation_extraction_prompt

9. fluency_evaluation_prompt
10. si_expression_evaluation_prompt

11. anchor_judgement_prompt
12. event_judgement_prompt
13. relation_judgement_prompt

14. global_fidelity_review_prompt
15. dimension_scoring_prompt
16. final_summary_prompt
```

这里不再保留旧的“原文—译文联合切分 Prompt”。

也不强制保留独立的 `target_sentence_segmentation_prompt`。因为译文切分已经由 `target_aligned_segmentation_prompt` 完成，它直接输出 `eval_units`，更符合后续评估需要。

## 26. Prompt 输入隔离原则

每个 Prompt 只能看到自己需要的字段。

源文切分只看 `source_text`。

源文 anchor 抽取只看 `source_units`。

源文 event 抽取只看 `source_units`。

源文 relation 抽取只看 `source_units` 和 `source_events`。

译文对齐式切分看 `source_units` 和完整 `si_translation`。

译文 anchor 抽取只看 `eval_unit_id` 和 `target_unit`。

译文 event 抽取只看 `eval_unit_id` 和 `target_unit`。

译文 relation 抽取只看 `eval_units.target_unit` 和 `target_events`。

fluency 只看完整 `si_translation`。

SI expression 看完整 `source_text` 和完整 `si_translation`。

anchor judgement 看 `eval_units`、`source_anchors` 和 `target_anchors`。

event judgement 看 `eval_units`、`source_events` 和 `target_events`。

relation judgement 看 `eval_units`、`source_relations`、`target_relations`、`source_events` 和 `target_events`。

global review 看完整 source、完整 target 和已有 judgement，不重新自由评分。

dimension scoring 只看 judgement、issue 和 review，不重新读取原文译文自由判错。

final summary 只看分数、judgement、issue 和 review，不新增错误。

## 27. 代码层职责

代码层可以做：

```text
1. 读取 JSONL。
2. 写入 JSONL。
3. 调用大模型。
4. 合并字段。
5. 检查 JSON 是否可解析。
6. 检查必填字段是否存在。
7. 检查 ID 是否重复。
8. 检查 source_units 拼接是否等于 source_text。
9. 检查 eval_units 中所有 target_unit 拼接是否等于 si_translation。
10. 检查每个 source_unit_id 是否在 eval_units 中出现一次且仅一次。
11. 检查 source_unit_ids 是否为相邻连续源文单元。
12. 检查 evidence_span 是否出现在对应 source_unit 或 target_unit 中。
13. 检查 judgement 是否覆盖每个 source_anchor、source_event、source_relation。
14. 检查分数是否在 0 到 100 之间。
15. 按固定权重计算 final_score。
16. 断点续跑。
17. 记录失败样本。
```

代码层不做：

```text
1. 不判断翻译是否正确。
2. 不用字符串匹配判断 anchor 是否等价。
3. 不用规则判断 event 是否保留。
4. 不用规则判断 relation 是否正确。
5. 不自动扣语义分。
6. 不根据参考译文判错。
```

代码层的规则是结构规则，不是语义评分规则。

## 28. 多系统评测方式

多系统评测时，流程如下：

```text
source_text
  ↓
source_card 只生成一次

system A si_translation
  ↓
target_eval_card A
  ↓
final_result A

system B si_translation
  ↓
target_eval_card B
  ↓
final_result B

system C si_translation
  ↓
target_eval_card C
  ↓
final_result C
```

所有系统共享同一个 `source_card`。这保证不同系统面对同一套 source units、source anchors、source events 和 source relations。

每个系统的 `eval_units` 不共享，因为它依赖该系统自己的译文切分和对齐。

## 29. 当前版本不做的内容

当前版本不评估真实同传延迟。

当前版本不评估 partial 输出稳定性。

当前版本不评估字幕闪烁。

当前版本不评估音频质量。

当前版本不评估系统 ASR。

当前版本不使用时间戳。

当前版本不把参考译文作为判错依据。

当前版本不设置 anchor、event 或 relation 的 1、2、3 重要程度。

当前版本不做传统实体类别分类。

当前版本不使用代码规则判断语义正确性。

当前版本不让最终评分阶段新增错误。

## 30. v0.3 的核心结论

v0.3 的核心方案是：

源文只做一次无损句子级切分，形成共享的 `source_units`。源文 anchor、event 和 relation 都基于这套共享 `source_units` 生成，所有系统共享同一份源文底稿。

每个同传系统译文在共享 `source_units` 引导下进行对齐式无损切分，直接生成 `eval_units`。每个 `eval_unit` 包含一个或多个 `source_unit_ids` 和一个 `target_unit`。所有 `target_unit` 按顺序拼接后必须等于完整 `si_translation`，每个 `source_unit_id` 必须被覆盖一次且仅一次。

译文 anchor、event 和 relation 都基于 `eval_units.target_unit` 抽取，并绑定 `eval_unit_id`。它们只描述译文实际表达了什么，不判断是否正确。

内容忠实度判断基于 `eval_units` 完成。Anchor、event、relation judgement 分别比较源文结构和译文结构，判断是否正确、部分正确、错误、缺失或不确定。

Fluency 是完整译文维度，只看 `si_translation`。SI Expression 是完整同传表达维度，看完整 `source_text` 和完整 `si_translation`，但不重复判断 anchor、event 和 relation 忠实度。

最终评分基于五个维度：anchor fidelity 30 分，event fidelity 25 分，relation fidelity 20 分，fluency 15 分，SI expression 10 分。五维分数由大模型根据结构化证据生成，最终总分由固定权重加权计算。

这个版本的关键优势是：源文底稿稳定、系统间评估基准统一、译文切分直接服务于源文句子级评估、内容忠实度有局部证据范围、最终评分受结构化证据约束。