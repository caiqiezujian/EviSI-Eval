# Reference Relation Extraction

你在整个评测链路中的角色：**按 Source Relations 的顺序，逐项判断 Reference 参考译文中是否保留了对应关系。** 这是联合卡构建的第八步，也是联合卡最后一步。

你的输出将与 Source Relations 按位置合并，完成联合卡中 relations 的 reference 侧。

---

## Part A: 输入

1. **source_relations**：已冻结的 Source Relations（含 relation_id、type、summary、evidence、source_event_ids、importance）
2. **reference_events**：已对齐的 Reference Events（含 event_id、summary、evidence）
3. **reference_translation**：参考译文全文

---

## Part B: 核心规则

1. **数量相等**：`reference_relations.length == source_relations.length`
2. **顺序一致**：reference_relations 的顺序与 source_relations **完全一致**
3. **relation_id 一致**：每条 reference relation 的 `relation_id` 必须与对应 source relation 完全相同

---

## Part C: 如何判断 Reference 是否保留了 Relation

### C.1 先检查端点可用性

根据 source relation 的 `source_event_ids`，找到对应的 reference events。

如果 source relation 涉及的 event 在 reference_events 中对应的 evidence 为空（Reference 中没有该命题），则该 relation 的端点可能不可用。但 Reference 是较完整的人工翻译，通常不会缺失端点——仅在确实缺失时记录。

### C.2 再判断关系是否保留

阅读 source relation 的 `summary` 理解关系的类型和方向。然后在 Reference 译文中检查：
- Reference 是否表达了相同的逻辑关系？
- 关系方向是否一致？
- 关系类型是否一致或等价？

Reference 不必使用相同的连接词——只要语义上保留了同样的关系类型和方向即可。

### C.3 preserved 判断

- **true**：Reference 保留了该关系（类型和方向一致）
- **false**：Reference 未保留该关系（关系缺失、弱化到不可恢复、或方向改变）

### C.4 summary 要求

- 若 `preserved: true`：描述 Reference 中保留了怎样的关系及保留方式
- 若 `preserved: false`：说明 Reference 中缺失了什么、为什么关系不成立

---

## Part D: 字段规范

| 字段 | 说明 |
|------|------|
| `relation_id` | 必须与对应 source relation 相同 |
| `preserved` | true（保留了关系）或 false（未保留） |
| `summary` | preserved 时描述对应关系；未 preserved 时说明缺失内容 |

---

## Part E: 正反例

```
Source Relation:
  relation_id: "R1"
  type: "attribution"
  summary: "S2_E2 → attribution → S2_E3，李博士是方法描述的来源"
  source_event_ids: ["S2_E2", "S2_E3"]

Reference 译文：
  "李博士谈到用不同观测类型对不同模型域进行数据同化，这个方法很巧妙。"

→ Reference Relation:
  relation_id: "R1"
  preserved: true
  summary: "归属关系保留——'李博士谈到'明确了信息来源，后续'这个方法'的评价归属于李博士的观点"
  ✓
```

---

## Part F: 常见失败模式

1. **数量不对**：reference_relations 与 source_relations 长度不同
2. **relation_id 不匹配**：与对应 source relation 不同
3. **过度严格**：要求 Reference 使用和 Source 完全相同的连接词。译文可能用意合方式表达相同的逻辑关系
4. **漏判保留**：Reference 确实保留了关系但被判为 false
5. **summary 过于简单**：只写 "preserved" 或 "not preserved"，没有说明原因

---

## Part G: 输出前自检

1. reference_relations 数量是否等于 source_relations 数量？
2. 每条 relation_id 是否与对应 source relation 一致？
3. 是否检查了 endpoint events 在 Reference 中的可用性？
4. preserved 判断是否基于语义等价而非表面连接词？
5. summary 是否说明了判断理由？

---

## Part H: 输出 JSON

```json
{
  "sample_id": "sample_001",
  "reference_relations": [
    {
      "relation_id": "R1",
      "preserved": true,
      "summary": "归属关系保留——'李博士谈到'承载了 attribution，后续评价归属于李博士的观点"
    }
  ]
}
```

如果 source_relations 为空数组，输出 `"reference_relations": []`。
