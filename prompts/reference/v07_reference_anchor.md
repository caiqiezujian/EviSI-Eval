# Reference Anchor Extraction

你在整个评测链路中的角色：**基于 Source Anchors 和已对齐的 Reference segments，逐项输出 Reference 中对应的 Anchor 表达。** 这是联合卡构建的第六步。

你的输出将与 Source Anchors 按位置合并，形成联合卡中每条 Anchor 的 reference 侧。**数量和顺序必须与 Source 完全一致。**

---

## Part A: 输入

1. **source_segments**：已冻结的 Source 断句（含 seg_id、source_text）
2. **source_anchors**：已冻结的 Source Anchors（含 anchor_id、seg_id、type、text、evidence、importance）
3. **reference_segments**：已对齐的 Reference 断句（含 seg_id、reference_text）
4. **reference_translation**：参考译文全文

---

## Part B: 核心规则

1. **数量相等**：reference_anchors 总数 = source_anchors 总数
2. **顺序一致**：reference_anchors 顺序与 source_anchors **按位置一一对应**（第 i 条 reference anchor 对应第 i 条 source anchor）
3. **anchor_id 一致**：每条 reference anchor 的 `anchor_id` 必须与对应 source anchor 完全相同
4. **seg_id 一致**：每条 reference anchor 的 `seg_id` 必须与对应 source anchor 完全相同
5. **缺失处理**：Reference 中确实没有对应表达时，`text` 和 `evidence` 填空字符串 `""`

---

## Part C: 如何找到 Reference 中的对应

以 Source Anchor 为查询，在对应 Reference segment 中寻找目标语表达：

- **entity**：找到对应译名。`Dr. Li` → `李博士`、`ECMWF` → `ECMWF`
- **term**：找到对应术语译法。`data assimilation` → `数据同化`
- **quantity**：找到对应数值表达（允许单位转换，如实记录 Reference 的表达）
- **temporal**：找到对应时间表达
- **scope**：找到对应范围表达

Reference 可能用不同于 Source 字面形式的表达——找的是**语义对应**。Reference 表达与 Source 有差异时如实记录，不做对错判断。

---

## Part D: 正反例

```
Source Anchor: seg_id="S2", text="data assimilation", evidence="Data assimilation"
Reference segment S2: "数据同化并非通用方法。李博士谈到..."
  → anchor_id: "S2_A1", seg_id: "S2"
  → text: "数据同化", evidence: "数据同化"  ✓

Source Anchor: seg_id="S2", text="different model domains", evidence="different model domains"
Reference segment S2: "...用不同观测类型对不同模型域进行数据同化..."
  → text: "不同模型域", evidence: "不同模型域"  ✓

Source Anchor: seg_id="S2", text="some_missing_term"
Reference segment S2: 完全没有对应
  → text: "", evidence: ""  ✓（诚实留空，不编造）
```

---

## Part E: 字段规范

| 字段 | 说明 |
|------|------|
| `anchor_id` | 必须与对应 source anchor 相同 |
| `seg_id` | 必须与对应 source anchor 相同 |
| `text` | Reference 中对应表达的干净文本（无则 `""`） |
| `evidence` | Reference segment 中的逐字连续证据（无则 `""`） |

---

## Part F: 常见失败模式

1. **数量不对**：reference_anchors 与 source_anchors 总数不同
2. **顺序错位**：第 3 条对应到了第 2 条 source anchor
3. **anchor_id 不匹配**：与对应 source anchor 不同
4. **seg_id 不匹配**：写到了错误的 segment
5. **evidence 不是逐字**：写了"大概的意思"而非 reference_text 中的连续子串
6. **翻译而非记录**：写了"应该怎么翻译"而非 Reference 中实际出现的文本
7. **冗余补充**：Reference 中没有却编造了一个

---

## Part G: 输出前自检

1. 输出总数是否等于 source_anchors 总数？
2. 顺序是否与 source_anchors 完全一致（第 i 条对第 i 条）？
3. 每条 anchor_id 和 seg_id 是否与对应 source anchor 一致？
4. 每条 evidence 是否逐字存在于对应 reference segment 中？
5. 缺失的对应是否诚实留空？

---

## Part H: 输出 JSON

```json
{
  "sample_id": "sample_001",
  "reference_anchors": [
    {
      "anchor_id": "S1_A1",
      "seg_id": "S1",
      "text": "四维变分同化方法",
      "evidence": "四维变分同化方法"
    },
    {
      "anchor_id": "S2_A1",
      "seg_id": "S2",
      "text": "数据同化",
      "evidence": "数据同化"
    },
    {
      "anchor_id": "S2_A2",
      "seg_id": "S2",
      "text": "李博士",
      "evidence": "李博士"
    },
    {
      "anchor_id": "S2_A3",
      "seg_id": "S2",
      "text": "不同的观测类型",
      "evidence": "不同的观测类型"
    },
    {
      "anchor_id": "S2_A4",
      "seg_id": "S2",
      "text": "不同模型域",
      "evidence": "不同模型域"
    }
  ]
}
```
