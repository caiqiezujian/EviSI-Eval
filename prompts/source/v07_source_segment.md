# Source Segmentation

你在整个评测链路中的角色：**将源语 transcript 无损切分为稳定的语义上下文段。** 这是联合卡构建的第一步。后续所有步骤（Anchor、Event、Relation、Reference 对齐、SI 匹配）都依赖你输出的 segment 边界。

你只做断句。不抽取 Anchor/Event/Relation，不看任何译文，不评分。

---

## Part A: 切分目标

将 `source_text` 切分为若干 segment。目标粒度：**通常约 2 个完整句子，允许 1-3 句弹性。**

segment 是"一段连贯的上下文窗口"，不是 Event 粒度——一个 segment 可以包含多个 Event。

---

## Part B: 切分原则（按优先级）

### B.1 话题完整优先

因果链（because/so/therefore）、指代链（it/this/that 指向上文）、转折链（but/however/although）应尽量放在同一个 segment 内。**不要在逻辑关系中间切分。**

### B.2 语义边界切分

在以下位置切分：
- 明显的话题转换（说话者进入新论点）
- 前一语义单元完整结束
- 问答对之间的自然停顿
- 对话场景中说话者切换

### B.3 粒度弹性

允许 1-3 句变化：
- 独立长复杂句 → 可单独成段
- 两个紧密关联短句 → 合为一段
- 三个连续简单并列陈述 → 可放一段
- **不要为追求"恰好 2 句"而破坏语义边界**

### B.4 口语特征处理

口语 transcript 中的填充（um/uh/you know）、重复（the the project）、自我修正（15, no, 50 percent）不构成独立切分理由。留在所属 segment 内。

---

## Part C: 硬约束

1. **无损拼接**：所有 segment 按 seg_id 顺序直接拼接，必须逐字符等于原始 source_text。包括空格、换行、标点、填充、重复、残句和异常字符。
2. **不得改写**：segment 文本是原始文本的逐字切片，不得清洗、纠错、翻译、补词或删除任何字符。
3. **不得有空 segment**：每个 segment 必须有非空文本。
4. **连续编号**：seg_id 从 S1 开始连续编号（S1, S2, S3...），不得跳号。

---

## Part D: 正反例

```
✓ 正确：
  "Ensemble forecasting is not a universal solution. Dr. Li mentioned using
   different initialization methods across regional models, which was a
   clever approach."
  → 一个 segment：两句共享"Dr. Li 的方法"主题，第二句的 which 依赖第一句。

  "Okay, cool. Um, yeah, all right, are you done with your presentation,
   or is there anything else you want to add?"
  → 单独成段：话题从讨论技术切换到询问演示进度。

✗ 错误：
  "Dr. Li was very open about the fact that data assimilation isn't an area
   he's an expert on and this is okay."
  → 不要在 "and this is okay" 前切分。"this" 指向前半句的整个事实。
```

---

## Part E: 输出前自检

1. 所有 segment 拼接是否逐字符等于 source_text？
2. 粒度是否符合 ~2 句，语义边界是否完整？
3. 是否没有在逻辑关系（因果/指代/转折）中间切分？
4. seg_id 是否从 S1 连续编号无跳号？
5. 是否有空 segment？

---

## Part F: 输出 JSON

```json
{
  "sample_id": "sample_001",
  "source_segments": [
    {
      "seg_id": "S1",
      "source_text": "Ensemble forecasting combines multiple model runs to produce a probabilistic forecast. The method was originally developed for global weather prediction but has since been adapted for regional climate modeling. "
    },
    {
      "seg_id": "S2",
      "source_text": "Data assimilation integrates observations into numerical models. Dr. Li pointed out that variational methods, such as 3D-Var and 4D-Var, are widely used in operational centers, although their computational cost can be high. "
    },
    {
      "seg_id": "S3",
      "source_text": "Dr. Li openly admitted that data assimilation is not his primary expertise, and this is perfectly acceptable. It is important to be transparent when asked about topics outside your core domain. "
    }
  ]
}
```
