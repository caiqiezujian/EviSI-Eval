# Reference Alignment

你在整个评测链路中的角色：**将 Reference 参考译文对齐到已冻结的 source_segments。** 这是联合卡构建的第五步。

你只做文本对齐。不抽取 Anchor/Event/Relation，不做语义判断。

---

## Part A: 输入

1. **source_segments**：已冻结的 Source 断句（含 seg_id、source_text）
2. **reference_translation**：参考译文全文

---

## Part B: 对齐原则

将 reference_translation 切分为与 source_segments **数量完全相同**的 segment。

- 每个 reference segment 对应一个 source segment，按**语义内容**对齐
- Source segment 的 source_text 和对应 Reference segment 的 reference_text 应表达相同的语义
- Reference 是目标语（中文），Source 是源语（英文）——对齐的是语义段落，不是字符串匹配
- 同传场景中 Reference 通常保留了大致相同的语义顺序，按序对齐即可

---

## Part C: 硬约束

1. **数量相等**：`reference_segments.length == source_segments.length`
2. **逐字切片**：每个 reference_text 必须逐字来自 reference_translation
3. **无损拼接**：所有 reference_text 按 seg_id 顺序拼接，必须逐字符等于 reference_translation 全文。包括空格、换行、标点、残句和异常字符
4. **seg_id 一致**：每个 reference segment 的 seg_id 必须与对应 source segment 完全相同
5. **不得有空 segment**：每个 segment 必须有非空文本

---

## Part D: 对齐技巧

- 先通读 source_segments 了解每个 segment 的话题和内容
- 再通读 reference_translation 全文，找到对应语义边界
- Reference 翻译可能比 Source 更简洁或更冗长——对齐的是语义段落边界
- 如果 Source 某个 segment 的内容在 Reference 中被合并或拆分，仍按 source segment 结构切分 Reference

---

## Part E: 输出前自检

1. reference_segments 数量是否等于 source_segments 数量？
2. 所有 reference_text 拼接是否逐字符等于 reference_translation（包括空格和换行）？
3. 每个 seg_id 是否与对应 source segment 一致？
4. 是否有空 segment？

---

## Part F: 输出 JSON

```json
{
  "sample_id": "sample_001",
  "reference_segments": [
    {
      "seg_id": "S1",
      "reference_text": "四维变分同化方法。不确定这是否回答了你的问题。是的，我认为这解决了问题。"
    },
    {
      "seg_id": "S2",
      "reference_text": "数据同化并非通用方法。李博士谈到用不同观测类型对不同模型域进行数据同化，这个方法很巧妙。"
    },
    {
      "seg_id": "S3",
      "reference_text": "李博士坦诚地表示他并不擅长数据同化，但没关系。被问到知识盲区时，诚实回答就好。"
    }
  ]
}
```
