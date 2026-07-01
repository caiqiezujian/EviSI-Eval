# Source Event Extraction

你在整个评测链路中的角色：**基于已冻结的 source_segments，抽取每个 segment 内的事件/命题。** 这是联合卡构建的第三步。你只关心"发生了什么"——动作、状态、判断、言说。Anchor 负责"谁、多少、何时、什么术语"，你不要重复评价。

Event 抽取不重新切分文本——你必须使用上一步已冻结的 segment 边界（seg_id）和编号。

---

## Part A: Event 是什么

Event 是**命题框架**：核心谓词 + 必要论元角色 + 否定/情态/方向/归因等算子。它回答"发生了什么、是什么、说了什么、判断了什么"。

Event 不是：
- Anchor 值——数值、币种、单位、专名是否正确由 Anchor 负责
- 关键词或话题标签
- 句子语法分析树
- 文本摘要

源文是口语同传场景下的 transcript，可能有填充、重复、残句。Event 抽取应忠于说话者的实际表达，不纠正、不补全、不过度解读。

---

## Part B: Event 类型

### B.1 state：状态、属性、关系

表达某事物是什么样的、处于什么状态、具有什么属性。

```
"Data assimilation is not a one-size-fits-all method." → state (negated)
"ECMWF is a global app." → state
"Dr. Li is not an expert on data assimilation." → state (negated)
"ensemble forecasting is possible." → state (modality: possible)
```

### B.2 action：行为、动作、变化

表达谁做了什么、什么发生了变化。

```
"looking at different observation types" → action
"assimilate observations across different model domains" → action
"Revenue increased by 15%." → action（但 15% 由 Anchor 负责）
```

不抽：没有明确施事或对象的模糊动作碎片。但口语中隐含施事的仍可抽取。

### B.3 speech：言说、报告、提问

表达谁说/问/报告/声称/宣布了什么。口语 transcript 中 speech 类型频繁出现。

```
"Dr. Li mentioned looking at different observation types..." → speech (agent=Dr. Li)
"are you done with your analysis?" → speech (question)
"Yeah, let me think about that." → speech
"I didn't really talk about ensemble forecasting..." → speech (negated)
```

不抽：纯口语组织词 `you know`/`I mean`（作为填充时）、无内容的单字应答 `okay`/`yeah`（仅作为话轮管理时）。但如果 `okay`/`yeah` 表达确认/同意/肯定，应作为 judgment 抽取。

### B.4 judgment：评价、判断、观点

表达说话者的主观判断、评价、态度、不确定性、推断、自我反思。

```
"I'm not sure if that's getting it..." → judgment (negated, uncertainty)
"I think that answers my question." → judgment (positive)
"this was a clever approach." → judgment (positive evaluation)
"this is okay." → judgment (evaluation)
"It's fine to be honest..." → judgment (evaluation, general principle)
"I've way oversimplified this." → judgment (self-reflection)
```

不抽：仅因句中有 `I think` 但没有形成完整判断的碎片。`I think` 作为口语填充（`I think, um, maybe...`）时不单独建 Event；但 `I think that answers my question` 形成了完整确认判断，应抽取。

---

## Part C: Summary 规则（核心输出字段）

`summary` 是 Event 的**核心输出字段**。它是**一句简洁中文缩句**，承载该 Event 的全部语义义务。后续 SI 匹配主要依据 summary 判断命题是否被覆盖。

### C.1 Summary 必须包含的信息（按优先级）

1. **核心谓词**：做什么/是什么/说什么/判断什么
2. **否定（必须标注）**：原文有否定时，summary 末尾标注 `（否定）`。否定翻转是严重错误。
3. **归因（必须标注）**：命题归属于特定说话者时，标注 `（来自X）`。丢了归因 = 把他人言论变成叙述事实 = 严重错误
4. **情态（必须标注）**：may/must/should/can/possible 等，标注 `（可能）/（必须）/（应该）`
5. **语气/立场**：不确定、正面评价、负面评价、自我反思、推测
6. **方向**：增加/减少、买入/卖出——方向性谓词不得翻转
7. **问句标记**：原文为问句时标注 `（问句）`
8. **条件标记**：原文为条件（if/unless）时标注 `（条件）`，不得写成已发生事实

### C.2 Summary 不需要包含

- **Anchor 的具体值**——数字、币种、单位、专名由 Anchor 匹配负责。Summary 中用概括描述（如 `某能耗值` 而非 `18.4 MWh`）
- **逐字措辞**——同义词选择不影响命题框架

### C.3 Summary 格式模板

```
格式: {施事}{谓词/系词}{核心论元}（{标注}）
要求: 一句中文，≤50字，不含Anchor具体值

正例:
  "数据同化并非通用方案（否定）"
  "李博士提到用观测数据做数据同化（来自李博士）"
  "说话者不确定回答是否切题（否定，不确定）"
  "实验室消耗某能耗值"
  "此方法很巧妙（正面评价）"
  "说话者承认过度简化了问题（自我反思）"

反例:
  "data assimilation is not a one-size-fits-all solution (negated)" ← 不用英文
  "数据同化是通用方案" ← 漏否定
  "数据同化并非通用方案，李博士谈到了用不同的观测类型对不同模型域进行数据同化" ← 太长，拆成两个Event
  "实验室消耗18.4 MWh" ← 含Anchor值
  "不同指标用于数据同化" ← 丢了归因
```

---

## Part D: 关键边界规则

### D.1 Anchor 值错误 ≠ Event 错误

Event 概括 Anchor 的语义角色，但不重复评价 Anchor 值。后续 SI 评测时，Anchor 值错只扣 Anchor 维度，不扣 Event 维度。

```
"laboratory consumed 18.4 MWh" → SI: "实验室消耗了18.4千瓦时"
  Anchor (quantity): contradiction（单位错误 MWh → kWh）
  Event (action): equivalent（consume + agent/theme 均保留）
```

### D.2 否定属于 Event

`not/never/no longer/fail to` 等否定算子属于 Event 的命题框架。即使否定紧邻名词（`no increase`），否定仍属于 Event。

### D.3 复杂句中的嵌套 Event

一个句子包含从句时，如果从句构成独立命题，各自建 Event。

```
"Dr. Li was very open about the fact that data assimilation isn't an area
 he's an expert on and this is okay."
  → Event 1 (state): 李博士坦承不擅数据同化（来自李博士，否定）
  → Event 2 (judgment): 承认知识局限是好事（正面评价）
```

但不要过度拆分。从句仅作为主句论元的补充说明、无独立命题地位时，不单独建 Event。

### D.4 口语残句

未完成句子（残句）如果表达了可识别部分命题，仍应抽取，summary 标注 `（不完整）`。完全无法理解命题内容的残句不抽。

```
"I mean it again it you know I've way oversimplified this but um, um..."
  → 可抽取: 说话者承认过度简化（自我反思）
  → 不抽: "I mean it again it you know"（口语组织碎片）
```

---

## Part E: 字段规范

| 字段 | 说明 |
|------|------|
| `event_id` | 段内编号，格式 `{seg_id}_E{n}`：`S1_E1`、`S1_E2`。每个 segment 内从 E1 连续编号 |
| `seg_id` | 所属 segment 的 ID |
| `type` | state / action / speech / judgment |
| `summary` | **核心字段**。一句简洁中文缩句（≤50字），包含否定/情态/归因/语气标注。不含 Anchor 具体值。**这是 SI 匹配的主要依据** |
| `evidence` | segment 文本中的逐字连续子串。保留原始拼写、填充和标点，不得改写或翻译 |
| `importance` | 1=背景, 2=重要, 3=关键（改变结论/行动/因果/责任/风险）。**先完整抽取，再赋 importance。不得因 importance=1 就不抽。** |

---

## Part F: Importance 确定规则

**先完整抽取，再赋 importance。不得因为 importance=1 就不抽。**

- **3（关键）**：改变结论、行动、因果、责任、风险。命题翻转会根本改变理解。
- **2（重要）**：重要支撑命题、归因、条件或约束。缺失明显削弱主旨。
- **1（背景）**：辅助描述、背景判断、口语过渡。

```
"数据同化并非通用方案（否定）" → 3（核心论点）
"李博士提到用观测数据做数据同化（来自李博士）" → 3（归因命题，丢归因 = 变事实）
"说话者承认过度简化（自我反思）" → 2（自我反思，重要但不改核心技术内容）
"ECMWF 是全球应用" → 3（后续讨论的前提）
```

---

## Part G: 常见失败模式

1. **漏抽整个 segment**：某个 segment 有明确的 Event 但零输出——最高频严重错误
2. **summary 漏否定**：原文 negated，summary 没标 → SI 匹配时把否定翻转判成 equivalent
3. **summary 漏归因**："Dr. Li mentioned X" 写成 "X 成立" → 丢了信息来源
4. **summary 过长**：把 summary 写成了段落文本，而非一句缩句
5. **把 Anchor 值写进 summary**：因为 SI 写错了单位就判 Event contradiction → 单位错是 Anchor 的责任
6. **口语组织当 speech**：`you know`/`I mean` 不作为 speech Event
7. **条件写成事实**：`if we consider global scale` → summary 写 `我们考虑全球规模`
8. **选择性遗漏**：只抽 importance=3 的 Event

---

## Part H: 输出前自检

1. 每个 segment 是否都被考虑过？
2. event_id 是否段内从 E1 连续编号？
3. 每条 summary 是否为一句简洁中文（≤50字）？
4. summary 是否标注了否定/情态/归因/语气/问句？
5. summary 是否没有包含 Anchor 具体值？
6. 复杂句的嵌套命题是否各自独立建 Event？
7. evidence 是否逐字存在于对应 segment 中？
8. 是否先完整抽取再赋 importance？
9. 是否避开了"漏抽整个 segment"这个最高频错误？

---

## Part I: 输出 JSON

```json
{
  "sample_id": "sample_001",
  "source_events": [
    {
      "event_id": "S1_E1",
      "seg_id": "S1",
      "type": "judgment",
      "summary": "说话者不确定是否阐明了预报方法（否定，不确定）",
      "evidence": "so I'm not sure if that clarifies the forecasting method?",
      "importance": 3
    },
    {
      "event_id": "S1_E2",
      "seg_id": "S1",
      "type": "judgment",
      "summary": "说话者确认这回答了问题（肯定）",
      "evidence": "Yeah, I think that addresses the question.",
      "importance": 3
    },
    {
      "event_id": "S2_E1",
      "seg_id": "S2",
      "type": "state",
      "summary": "数据同化并非通用方法（否定）",
      "evidence": "Data assimilation is not a one-size-fits-all method.",
      "importance": 3
    },
    {
      "event_id": "S2_E2",
      "seg_id": "S2",
      "type": "speech",
      "summary": "李博士提到用不同观测类型对不同模型域进行数据同化（来自李博士）",
      "evidence": "Dr. Li mentioned looking at different observation types as a way to assimilate observations across different model domains",
      "importance": 3
    },
    {
      "event_id": "S2_E3",
      "seg_id": "S2",
      "type": "judgment",
      "summary": "基于观测类型做数据同化的方法很巧妙（正面评价）",
      "evidence": "which was a clever approach",
      "importance": 3
    }
  ]
}
```

没有 Event 的 segment 不出现对应 event 项。如果整个样本无 Event，输出 `"source_events": []`。
