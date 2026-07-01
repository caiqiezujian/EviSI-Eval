# Source Relation Extraction

你在整个评测链路中的角色：**基于已冻结的 source_segments 和 source_events，抽取 Event 之间的逻辑关系。** 这是联合卡构建的第四步。

Relation 层只抽取已经存在的 Source Events 之间的语义连接。它回答"两个命题之间是否存在会改变理解的逻辑关系"，不回答实体值是否正确（Anchor），也不重新抽取事件（Event）。

**默认没有 Relation。** Relation 是稀疏结构——没有充分证据时必须输出空数组。不得为了让图看起来完整而制造关系。

---

## Part A: Relation 成立的五道门

对每个候选关系，按顺序检查。**缺一不可：**

```
Q1 端点门：是否连接至少两个不同的已抽取 Source Event？
  否 → 不抽取。必须是两个已有 Event 之间的连接。

Q2 方向门：两个端点的角色和方向是否明确？
  否 → 不抽取。只是不清楚的语义联想（"A 和 B 有关"）。

Q3 信息增量门：该关系是否改变两个 Event 合在一起的解释？
  否 → 不抽取。可能只是并排陈述。

Q4 证据门：是否存在逐字显式 cue（连接词），或唯一且强度 ≥0.85 的强语义蕴含？
  否 → 不抽取。不能靠常识推断关系。

Q5 排除门：是否只是相邻、顺序、问答、话轮转换、同话题或常识推理？
  是 → 不抽取。这些不是逻辑关系。
```

尤其不能把"看起来有关"当作 Relation——必须能说清楚它是哪一种关系、方向是什么、证据在哪里。

---

## Part B: 16 类 Relation 的严格门槛

### B.1 cause_effect：因果
文本断言 A 导致/引发/促成/造成 B。
- 显式 cue：`because`、`therefore`、`as a result`、`due to`、`lead to`、`导致`、`因此`
- **不抽**：A 先发生 B 后发生但没有因果断言；`because` 只是口语填充

### B.2 condition_consequence：条件-结果
A 是 B 成立/发生/执行的条件。
- 显式 cue：`if`、`unless`、`provided that`、`only if`、`如果`、`除非`
- **不抽**：间接问句中的 `if/whether`；`if any` 局部限定

### B.3 purpose：目的
A 是为了实现 B，B 是 A 的目的。
- 显式 cue：`to`（目的用法）、`in order to`、`so that`、`为了`
- **不抽**：普通不定式补足语；实际结果误当目的

### B.4 concession：让步
尽管 A 成立，B 仍成立——预期被违背。
- 显式 cue：`although`、`despite`、`even though`、`尽管`、`即使`
- **不抽**：普通 contrast（仅对立无让步）

### B.5 contrast：对立
A 与 B 在同一比较维度上明确对立。
- 显式 cue：`but`（语义对立）、`whereas`、`while`、`however`、`但是`、`而`
- **不抽**：两个内容不同但无共同维度的句子；话题转换

### B.6 temporal_sequence：时序
文本断言 A 先于 B、B 后于 A。
- 显式 cue：`before`、`after`、`then`、`随后`、`之前`、`之后`
- **不抽**：文本先写 A 后写 B（叙述顺序 ≠ 时序）

### B.7 temporal_overlap：同时
A 与 B 同时/重叠发生。
- 显式 cue：`while`、`during`、`at the same time`、`同时`
- **不抽**：同一段落出现不等于同时

### B.8 conjunction：联合
A 与 B 被明确组合为同一决策/清单/方案。
- 显式 cue：`both...and`、`as well as`
- **不抽**：每个 `and` 都建 conjunction

### B.9 progression：递进
B 在同一维度上比 A 更进一步/升级/扩展。
- 显式 cue：`furthermore`、`not only...but also`、`进一步`、`不仅...还`

### B.10 similarity：相似
A 与 B 被文本明确表述为相似/相同/可类比。
- 显式 cue：`similarly`、`like`、`as with`、`类似`

### B.11 difference：差异
A 与 B 被明确表述为不同/区分。
- 显式 cue：`different from`、`unlike`、`distinguish`、`不同于`

### B.12 degree：程度比较
A 与 B 存在程度/强弱/大小/优先级关系。
- 显式 cue：`more than`、`less than`、`higher than`、`比...更`

### B.13 elaboration：具体化
B 对 A 进行具体化/解释/重述/展开。
- 显式 cue：`that is`、`in other words`、`namely`、`也就是说`、`具体来说`
- **不抽**：话题延续；B 只是同段落下一句

### B.14 attribution：归属
某命题明确归属于来源/说话者/研究/报告。**口语 transcript 中最常见。**
- 显式 cue：`said`、`according to`、`mentioned`、`表示`、`根据`
- **不抽**：Event 已完整记录 "Elena reported X" 且 X 不另建 Event

### B.15 exemplification：举例
B 是 A 所述类别/原则/现象的实例。
- 显式 cue：`for example`、`such as`、`including`、`例如`、`比如`

### B.16 conclusion：结论
B 是从 A 推出的结论/建议/决定/总结。
- 显式 cue：`therefore`、`so`（结论用法）、`in conclusion`、`因此`、`所以`
- **不抽**：最后一句自动当结论；`so` 只是口语组织词

---

## Part C: 强制假阳性排除

以下情况即使有表面连接词，也通常不抽 Relation：

1. 问句后出现回答（话轮转换）
2. 说话人轮次切换
3. 两句讨论同一主题但没有逻辑连接
4. A 先写 B 后写（仅叙述顺序）
5. `and`/`so`/`then`/`but` 只是口语组织词
6. 两句内容不同但没有共同比较维度
7. 为每个相邻 Event 创建 temporal_sequence 或 elaboration
8. A→B 成立后自动添加 A→C（传递推理）
9. 把 Anchor 的数值比较误建为 Event Relation
10. 把 Event 内部否定/情态/范围误建为 Relation

---

## Part D: Relation 与 Event 的边界

```
Source: "Sales rose because demand recovered."
  Event 1: 销售增长
  Event 2: 需求恢复
  Relation: cause_effect（需求恢复 → 销售增长）

不要把 "because demand recovered" 全塞进 Event 1 后就不建 Relation。
也不要在没有两个独立端点 Event 的情况下硬建 Relation。
```

连接词只改变单个 Event 内部的情态/否定/范围 → 属 Event operator，不是 Relation：
- `may increase` → Event modality
- `did not approve` → Event negation
- `only applies to children` → Event/Anchor scope

---

## Part E: 字段规范

| 字段 | 说明 |
|------|------|
| `relation_id` | R1、R2... 连续编号。不过度编号——大多数样本 Relation 数量为 0-3 |
| `type` | 必须是上述 16 类之一 |
| `summary` | 一句中文描述关系，格式：`{端点A} → {关系类型} → {端点B}` |
| `evidence` | 承载该关系证据的原文逐字片段 |
| `source_event_ids` | 涉及的 event ID 列表（至少两个） |
| `importance` | 1=背景, 2=重要, 3=关键。不要因为 cue 明显就给高分——importance 取决于关系对理解的影响 |

---

## Part F: 常见失败模式

1. **为相邻 Event 自动建边**：默认无 Relation，不要把相邻当因果/时序
2. **传递推理**：A→B 和 B→C 成立，不自动添加 A→C
3. **把口语 `so` 当结论**：`so` 在口语中经常只是话轮组织词
4. **漏掉 attribution**：口语 transcript 中 `Dr. Li mentioned/said/X reported` 是高频 Relation
5. **把问句-回答当 Relation**：问答是话轮结构，不是逻辑关系
6. **把 Event operator 当 Relation**：`did not increase` 的否定在 Event 内

---

## Part G: 输出前自检

1. 是否默认从空关系开始，而非从相邻 Event 自动连边？
2. 每条 Relation 是否至少连接两个已有 Source Event？
3. type 是否属于 16 类且门槛满足？
4. 方向是否能用 event_id 清楚说明？
5. evidence 是否逐字存在？
6. 是否排除了问答、话轮、同话题、普通顺序和常识推理？
7. source_event_ids 是否只列实际端点，没有编造 ID？
8. 空结果是否诚实输出 `[]`？

---

## Part H: 输出 JSON

```json
{
  "sample_id": "sample_001",
  "source_relations": [
    {
      "relation_id": "R1",
      "type": "attribution",
      "summary": "S2_E2（李博士的陈述）→ attribution → S2_E3（方法描述），李博士是数据同化方法描述的来源",
      "evidence": "Dr. Li mentioned looking at different observation types as a way to assimilate observations across different model domains",
      "source_event_ids": ["S2_E2", "S2_E3"],
      "importance": 2
    }
  ]
}
```

没有 Relation 时输出 `"source_relations": []`。
