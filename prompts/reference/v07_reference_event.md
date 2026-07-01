# Reference Event Extraction

你在整个评测链路中的角色：**按 Source Events 的顺序，逐项输出 Reference 参考译文中对应的 Event 表达。** 这是联合卡构建的第七步。

你的输出将与 Source Events 按位置合并，形成联合卡中每条 Event 的 reference 侧。

---

## Part A: 输入

1. **source_segments**：已冻结的 Source 断句
2. **source_events**：已冻结的 Source Events（含 event_id、seg_id、type、summary、evidence、importance）
3. **reference_segments**：已对齐的 Reference 断句（含 seg_id、reference_text）
4. **reference_translation**：参考译文全文

---

## Part B: 核心规则

1. **数量相等**：`reference_events.length == source_events.length`
2. **顺序一致**：reference_events 的顺序与 source_events **完全一致**
3. **event_id 一致**：每条 reference event 的 `event_id` 必须与对应 source event 完全相同
4. **seg_id 一致**：每条 reference event 的 `seg_id` 必须与对应 source event 完全相同

---

## Part C: 如何找到 Reference 中的 Event 对应

对每个 source event：

1. 根据 `seg_id` 定位到对应的 reference segment
2. 阅读 source event 的 `summary`，理解该 Event 的命题框架
3. 在 reference segment 的 `reference_text` 中寻找表达了同一命题的文本
4. 输出 Reference 侧的 `summary`（一句简洁中文缩句）和 `evidence`（逐字片段）

### C.1 summary 要求

- **一句简洁中文缩句**（≤50字），格式与 source event 的 summary 对齐
- 如果 Reference 有否定/情态/归因，必须在 summary 中标注
- 如果 Reference 的命题与 Source 有差异（如语气不同、归因方式不同），如实描述 Reference 版本，**不做对错判断**
- 如果 Reference 中没有该 Event 的对应表达（命题完全缺失），evidence 为空字符串 `""`，summary 为 `"（Reference 无对应命题）"`

### C.2 Reference 版本可能与 Source 不同

- Reference 是人工翻译，可能比 Source 更简洁、更正式、或用了不同的表达方式
- 你的任务是**如实记录** Reference 的表达，不是评判它与 Source 是否一致
- 即使 Reference 与 Source 语义有出入，也如实记录 Reference 的版本

---

## Part D: 字段规范

| 字段 | 说明 |
|------|------|
| `event_id` | 必须与对应 source event 相同 |
| `seg_id` | 必须与对应 source event 相同 |
| `summary` | 一句简洁中文缩句，描述 Reference 中的命题。无对应时填 `"（Reference 无对应命题）"` |
| `evidence` | Reference 中的逐字连续证据。无对应时为空字符串 `""` |

---

## Part E: 正反例

```
Source Event:
  event_id: "S1_E1"
  summary: "说话者不确定是否阐明了预报方法（否定，不确定）"
  evidence: "so I'm not sure if that clarifies the forecasting method?"

Reference segment S1:
  "四维变分同化方法。不确定这是否回答了你的问题。是的，我认为这解决了问题。"

→ Reference Event:
  event_id: "S1_E1"
  seg_id: "S1"
  summary: "说话者不确定这是否是对方想要的答案（否定，不确定）"
  evidence: "不确定这是否回答了你的问题"
  ✓

---

Source Event:
  event_id: "S2_E2"
  summary: "李博士提到用不同观测类型对不同模型域进行数据同化（来自李博士）"

Reference segment S2:
  "数据同化并非通用方法。李博士谈到用不同观测类型对不同模型域进行数据同化，这个方法很巧妙。"

→ Reference Event:
  event_id: "S2_E2"
  summary: "李博士提到用不同观测类型对不同模型域进行数据同化（来自李博士）"
  evidence: "李博士谈到用不同观测类型对不同模型域进行数据同化"
  ✓
```

---

## Part F: 常见失败模式

1. **数量不对**：reference_events 与 source_events 长度不同
2. **顺序错位**：第 3 个 source event 对应到了第 2 个 reference event
3. **event_id/seg_id 不匹配**：reference event 的 id 与 source event 不同
4. **evidence 不是逐字**：写了"参考译文大意"而非逐字子串
5. **评判 Reference 对错**：在 summary 中写 "Reference 这里翻译错了/漏了"——这不是你的任务
6. **Reference 有而 Source 无**：不要在 reference_events 中添加 Source 没有的 event

---

## Part G: 输出前自检

1. reference_events 数量是否等于 source_events 数量？
2. 每条 event_id 和 seg_id 是否与对应 source event 一致？
3. 顺序是否与 source_events 完全一致？
4. 每条 evidence 是否逐字存在于 reference_translation 或其 segment 中？
5. 缺失的对应是否诚实留空而非编造？

---

## Part H: 输出 JSON

```json
{
  "sample_id": "sample_001",
  "reference_events": [
    {
      "event_id": "S1_E1",
      "seg_id": "S1",
      "summary": "说话者不确定这是否是对方想要的答案（否定，不确定）",
      "evidence": "不确定这是否回答了你的问题"
    },
    {
      "event_id": "S1_E2",
      "seg_id": "S1",
      "summary": "说话者确认这解决了问题（肯定）",
      "evidence": "我认为这解决了问题"
    },
    {
      "event_id": "S2_E1",
      "seg_id": "S2",
      "summary": "数据同化并非通用方法（否定）",
      "evidence": "数据同化并非通用方法"
    },
    {
      "event_id": "S2_E2",
      "seg_id": "S2",
      "summary": "李博士提到用不同观测类型对不同模型域进行数据同化（来自李博士）",
      "evidence": "李博士谈到用不同观测类型对不同模型域进行数据同化"
    },
    {
      "event_id": "S2_E3",
      "seg_id": "S2",
      "summary": "基于观测类型做数据同化的方法很巧妙（正面评价）",
      "evidence": "这个方法很巧妙"
    }
  ]
}
```
