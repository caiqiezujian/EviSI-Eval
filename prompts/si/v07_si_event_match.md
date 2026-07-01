# SI Event Matching

你在整个评测链路中的角色：**逐 Source Event 判断 SI 同传译文是否覆盖了对应的命题框架。** 这是 SI 评测的第三步。

Event 只评价命题框架（核心谓词、必要论元角色、否定/情态/归因/方向/语气），不评价 Anchor 值。

---

## Part A: 输入

1. **source_events**：Source Events（含 event_id、seg_id、type、summary、evidence）
2. **joint_events**：联合卡 Events（含 event_id、seg_id、type、source_summary、source_evidence、reference_summary、reference_evidence、importance）
3. **si_segments**：已对齐的 SI segment 文本（含 seg_id、si_text）
4. **si_translation**：SI 译文全文

---

## Part B: 核心规则

1. **数量相等**：`event_matches.length == joint_events.length`
2. **顺序一致**：顺序与 joint_events 完全一致
3. **event_id 一致**：每条 match 的 `event_id` 与对应 joint event 相同

---

## Part C: 五个 match 值的精确判断标准

Event 关注**命题框架**：谁做了什么/是什么/说了什么/判断了什么 + 否定/情态/归因/方向/语气。

Event 不关注 Anchor 值：数字、单位、币种、专名是否精确由 Anchor 维度负责。

### equivalent（1.0 分）

SI 等价覆盖了 Event 的命题框架。满足以下**全部**条件：
1. 核心谓词保留（同义或可互换）
2. 必要论元角色保留（agent、theme、content 等关键角色在 SI 中存在对应）
3. 否定保留（原文 negated → SI 也 negated；原文 positive → SI 也 positive）
4. 归因保留（原文 attributed to X → SI 也明确归属于 X）
5. 方向保留（增加/减少 等方向性谓词不翻转）
6. 问句保留为问句
7. 条件保留为条件（不误写成事实）

SI 与 Reference 的措辞不同但命题等价 → equivalent。

```
Source: "说话者不确定是否阐明了预报方法（否定，不确定）"
SI: "我不确定这是否阐明了预报方法"
→ equivalent ✓（否定和不确定性均保留）

Source: "李博士提到用观测数据做数据同化（来自李博士）"
SI: "李博士提到查看不同的观测类型，以此对不同模型域进行数据同化"
→ equivalent ✓（归因保留，命题完整）

Source: "数据同化并非通用方法（否定）"
SI: "数据同化并非适用于所有情况"
→ equivalent ✓（否定保留，表述不同但命题等价）
```

### partial（0.5 分）

SI 保留了核心命题但有关键缺失或弱化：
- 归因弱化（明确归属于 Dr. Li → 模糊被动 `据悉`/`据说`）
- 语气弱化（strong certainty → weak suggestion）
- 部分论元丢失但核心命题仍可恢复
- 问句变陈述但内容仍在
- 命题被压缩但核心方向保留

```
Source: "李博士提到用观测数据做数据同化（来自李博士）"
SI: "使用不同观测数据进行数据同化是一种方法"
→ partial（归因丢失，命题从"李博士说"变成了叙述事实）

Source: "说话者不确定是否阐明了预报方法（否定，不确定）"
SI: "这也许阐明了预报方法"
→ partial（不确定性变为可能性，语气改变但未完全翻转）
```

### contradiction（0.0 分）

SI 表达了与 Source 明确冲突的命题：
- **否定翻转**：原文 negated → SI positive（或反之）——最严重的 Event 错误
- **谓词反转**：consume → generate、increase → decrease、approve → reject
- **归因翻转**：Dr. Li 说的话 → 变成说话者本人的陈述
- **方向翻转**：买入 → 卖出、收入 → 支出
- **条件变事实**：`if X then Y` → `X happened, Y happened`

```
Source: "数据同化并非通用方法（否定）"
SI: "数据同化是通用方法"
→ contradiction（否定翻转！negated → positive）
```

### missing（0.0 分）

SI 完全没有对应命题。在对应 SI segment 中找不到该 Event 的任何痕迹。

### uncertain

有证据但无法稳定判断。**只在确实无法判断时使用。**

---

## Part D: 关键边界规则

### D.1 Anchor 值错误 ≠ Event 错误

即使 SI 中 Anchor 值错误（如单位错、数字错），只要命题框架正确，Event 仍应判 equivalent。

```
Source Event: 实验室消耗某能耗值
Source Anchor: 18.4 MWh
SI: "实验室消耗了18.4千瓦时"
  → Anchor (quantity): contradiction（MWh → kWh 单位错）
  → Event (action): equivalent（consume + agent/theme 均保留）
  Event 不因为 Anchor 值错而被扣分！
```

### D.2 否定、情态、归因 必须在 Event 维度检查

这三者是命题框架的组成部分：
- 否定翻 → Event contradiction
- 情态丢 → Event partial/contradiction
- 归因丢 → Event partial（除非归因丢失改变了命题性质 → contradiction）

---

## Part E: 字段规范

| 字段 | 说明 |
|------|------|
| `event_id` | 必须与对应 joint event 相同 |
| `match` | equivalent / partial / contradiction / missing / uncertain |
| `si_summary` | SI 中对应命题的一句简洁中文缩句（≤50字）。无则为 `""` |
| `si_evidence` | SI 中的逐字连续证据（无则为 `""`） |
| `brief` | 一句简短判断理由（≤50字） |

---

## Part F: 常见失败模式

1. **因 Anchor 值错扣 Event 分**：SI 单位错了就在 Event 判 contradiction——最严重的评分错误
2. **否定漏检**：SI 丢了否定但被判 equivalent
3. **归因漏检**：丢了 Dr. Li 的归因但被判 equivalent
4. **以 Reference 为准绳**：Reference 的 summary 怎么写就要求 SI 也怎么写
5. **数量不对或顺序错位**
6. **evidence 不逐字**

---

## Part G: 输出前自检

1. event_matches 数量是否等于 joint_events 数量？
2. 每条 event_id 是否与 joint event 一致？
3. 否定/情态/归因是否逐一检查？
4. 是否避开了"因 Anchor 值错扣 Event 分"？
5. 是否以 Source 为权威而非 Reference？
6. contradiction 是否有明确的命题冲突证据？

---

## Part H: 输出 JSON

```json
{
  "sample_id": "sample_001",
  "event_matches": [
    {
      "event_id": "S1_E1",
      "match": "equivalent",
      "si_summary": "说话者不确定是否阐明了预报方法（否定，不确定）",
      "si_evidence": "我不确定这是否阐明了预报方法",
      "brief": "否定和不确定性均保留"
    },
    {
      "event_id": "S1_E2",
      "match": "equivalent",
      "si_summary": "说话者确认这回答了问题（肯定）",
      "si_evidence": "我想这回答了我的问题",
      "brief": "确认判断保留"
    },
    {
      "event_id": "S2_E1",
      "match": "equivalent",
      "si_summary": "数据同化并非适用于所有情况（否定）",
      "si_evidence": "数据同化并非适用于所有情况",
      "brief": "否定和核心谓词均保留"
    },
    {
      "event_id": "S2_E2",
      "match": "equivalent",
      "si_summary": "李博士提到用观测类型对不同模型域进行数据同化（来自李博士）",
      "si_evidence": "李博士提到查看不同的观测类型，以此对不同模型域进行数据同化",
      "brief": "归因和命题内容均保留"
    },
    {
      "event_id": "S2_E3",
      "match": "equivalent",
      "si_summary": "此方法很巧妙（正面评价）",
      "si_evidence": "这是个巧妙的方法",
      "brief": "正面评价保留"
    }
  ]
}
```
