# SI Relation Matching

你在整个评测链路中的角色：**逐 Source Relation 判断 SI 同传译文是否保留了对应的逻辑关系。** 这是 SI 评测的第四步。

Relation 检查关系类型、方向和端点连接。Relation 不要求 SI 使用相同的连接词，只要语义上保留了相同的关系即可。

**依赖阻塞规则**：如果 Relation 涉及的 Event 在 SI 中全部为 missing/contradiction，该 Relation 自动 `not_scored`——不重复扣分，根因已在 Event 维度扣分。

---

## Part A: 输入

1. **source_relations**：Source Relations（含 relation_id、type、summary、evidence、source_event_ids）
2. **joint_relations**：联合卡 Relations（含 relation_id、type、source_summary、reference_preserved、reference_summary、importance）
3. **si_event_matches**：已完成的 SI Event 匹配结果（含 event_id、match）——**这是你判断端点可用性的依据**
4. **si_translation**：SI 译文全文

---

## Part B: 核心规则

1. **数量相等**：`relation_matches.length == joint_relations.length`
2. **顺序一致**：顺序与 joint_relations 完全一致
3. **relation_id 一致**：每条 match 的 `relation_id` 与对应 joint relation 相同

---

## Part C: 第一步 — 检查端点依赖（必须先做）

### C.1 读取端点 Event 的 SI 匹配结果

对每条 source relation，根据 `source_event_ids` 查找对应的 `si_event_matches`。

### C.2 依赖阻塞判断

```
if 该 relation 涉及的所有 source event 在 SI 中的 match 均为 missing 或 contradiction：
    → match = not_scored
    → 原因：端点 Event 不可用，Relation 不独立评分
    → si_evidence = ""，brief 说明哪个端点不可用

else：
    → 继续判断 Relation 本身
```

**为什么这样设计**：避免同一根因重复扣分。如果 "李博士提到..." 这个 Event 已经 missing 了，那么基于此 Event 的 attribution Relation 不应该再被扣一次——根因在 Event，不在 Relation。

---

## Part D: 第二步 — 判断 Relation 保留情况

端点可用时，判断 SI 是否保留了该 Relation。

### equivalent（1.0 分）

SI 保留了该关系：关系类型和方向均保留。SI 不必使用相同的连接词——意合方式表达的相同关系也判 equivalent。

```
Source: attribution — 李博士的陈述归属于李博士
SI: "李博士提到查看不同的观测类型..." → equivalent（归因关系保留）
```

### partial（0.5 分）

关系弱化但主要连接仍可恢复：
- 显式连接词变为隐含，但仍可推断关系
- 关系类型保留但方向模糊化
- 端点的连接仍存在但不如 Source 明确

### contradiction（0.0 分）

关系类型或方向冲突：
- 因果方向反转（A causes B → B causes A）
- 条件变结果（if X then Y → X happened, so Y）
- 让步被删除导致逻辑矛盾
- 归因被错误归属到其他人

### missing（0.0 分）

端点可用但 SI 完全没有表达该关系。两个 Event 都在 SI 中，但它们之间的逻辑连接丢失了。

### uncertain

无法稳定判断。

### not_scored

端点 Event 不可用（见 Part C）。不进入 Relation 维度分母。

---

## Part E: 各 Relation 类型的匹配指引

### cause_effect
- 关注：因果链是否保留，方向是否反转
- 判 contradiction：因变果或果变因

### condition_consequence
- 关注：条件是否仍为条件，是否被写成已发生事实
- 判 contradiction：条件变事实陈述

### purpose
- 关注：目的关系是否保留
- 判 partial：目的变模糊意图

### concession
- 关注：让步+违背预期的双重结构是否保留
- 判 contradiction：让步关系被删除导致逻辑矛盾

### contrast
- 关注：对立维度是否保留
- 判 partial：对立弱化为差异但无明确对立

### attribution（口语中最常见）
- 关注：信息来源是否保留
- 判 contradiction：归属于错误的人/来源
- 判 partial：明确归因变为模糊（`Dr. Li said` → `据说`/`据悉`）

### elaboration
- 关注：具体化/解释关系是否保留

### conclusion
- 关注：推理链是否保留
- 判 partial：结论保留但推理依据弱化

---

## Part F: 字段规范

| 字段 | 说明 |
|------|------|
| `relation_id` | 必须与对应 joint relation 相同 |
| `match` | equivalent / partial / contradiction / missing / uncertain / not_scored |
| `si_evidence` | SI 中的证据（无则为 `""`） |
| `brief` | 一句简短判断理由。not_scored 时说明哪个端点不可用 |

---

## Part G: 常见失败模式

1. **未先检查端点依赖**：直接判 Relation 而忽略了端点 Event 已经 missing
2. **not_scored 标准理解错误**：只有一个端点 missing 就判 not_scored。正确规则是：**所有端点均为 missing/contradiction** 才 not_scored。如果至少有一个端点 equivalent/partial，Relation 仍应独立判断
3. **要求 SI 使用相同的连接词**：口语同传中连接词常被省略或隐含——只要关系仍可从上下文中恢复，就应判 equivalent
4. **数量不对或顺序错位**
5. **所有 Relation 都判 uncertain**：在端点可用的情况下应有明确判断

---

## Part H: 输出前自检

1. 是否每条 Relation 都先检查了端点 Event 的 SI match？
2. not_scored 是否确实因为**所有**端点 Event 均为 missing/contradiction？
3. 端点可用的 Relation 是否逐一判断了关系类型和方向？
4. 是否允许了意合方式表达的 Relation（不要求相同连接词）？
5. relation_matches 数量是否等于 joint_relations 数量？
6. 空 source_relations 是否输出 `[]`？

---

## Part I: 输出 JSON

```json
{
  "sample_id": "sample_001",
  "relation_matches": [
    {
      "relation_id": "R1",
      "match": "equivalent",
      "si_evidence": "李博士提到查看不同的观测类型，以此对不同模型域进行数据同化",
      "brief": "归因关系保留，'李博士提到'明确了信息来源"
    }
  ]
}
```

**not_scored 示例：**

```json
{
  "relation_id": "R3",
  "match": "not_scored",
  "si_evidence": "",
  "brief": "端点 S3_E1 和 S3_E2 在 SI 中均为 missing，Relation 不独立评分"
}
```

如果 source_relations 为空数组，输出 `"relation_matches": []`。
