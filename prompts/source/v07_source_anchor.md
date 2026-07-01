# Source Anchor Extraction

你在整个评测链路中的角色：**基于已冻结的 source_segments，抽取每个 segment 内的事实槽位（Anchor）。** 这是联合卡构建的第二步。

Anchor 回答"谁、什么专名、多少、何时、哪个术语、什么范围"。你只看 source_segments，不抽取 Event/Relation，不看任何译文，不评分。

---

## Part A: Anchor 是什么

Anchor 是**能够独立核验的事实槽位**。一个片段只有同时满足以下三问，才可以成为 Anchor：

```
Q1 类型：能否归入 entity / term / quantity / temporal / scope 之一？
  否 → 不抽取。可能是 Event 成分或普通修饰。

Q2 独立核验：脱离当前谓词后，是否仍可被识别、归一或比较？
  否 → 不抽取。它只是 Event 的内部成分（如谓词、普通宾语）。

Q3 信息义务：若同传遗漏或改变此信息，听众是否会失去一个可定位的事实？
  否 → 不抽取。它只是普通修饰或填充，不对同传构成义务。
```

例：`The observatory consumed 18.4 megawatt-hours.`
- `consumed`：Q1 失败，是谓词 → 不抽
- `observatory consumed energy`：Q2 失败，是不完整 Event → 不抽
- `18.4 megawatt-hours`：三问均通过 → quantity
- 整句：是 Event → 不抽

---

## Part B: 五类 Anchor 的精确边界

### B.1 entity：唯一身份或可识别对象

**应抽取：**
- 人名、明确人物称谓：`Elena Varga`、`the chief safety inspector`
- 有名称的机构、公司、政府、团队、项目：`World Bank`、`ECMWF`
- 地点与地理区域：`Geneva`、`European Union`
- 产品、政策、法规、会议、文件、活动的正式名称：`Orion-X7`
- 当前局部上下文中具有唯一指称、即使没有正式专名也能稳定识别的对象

**不应抽取：**
- 没有唯一身份的普通名词：`company`、`system`、`design`、`server`
- `someone`、`people`、`things` 等泛化对象
- 无 antecedent 的 `he`/`it`/`this`/`that`
- 仅因名词在主语位置就把它当实体
- 技术方法名 → 归入 term，不是 entity

**上下文唯一性必须谨慎**：`the company` 只有存在唯一且无歧义 antecedent 时才可抽。

### B.2 term：术语、方法和领域概念

**应抽取：**
- 技术、医学、法律、金融、政策、科研术语：`data assimilation`、`finite-volume discretization`、`Bayesian change-point detection`
- 缩写、算法名、指标名、方法名、架构名：`LRU cache`、`TCP/IP`、`F1 score`
- 在领域中具有稳定技术含义的复合概念：`multi-model ensemble`、`single point of failure`
- 过度泛化会产生明确精度损失的术语
- **反复出现的概念几乎一定是 term**——如果一个词/短语在多个 segment 中出现，且每次出现都指向同一技术概念，每次出现分别建 Anchor

**不应抽取：**
- 仅因出现在技术文本中的普通词：`approach`、`system`、`problem`、`method`
- 普通动作的名词化表达，除非形成领域固定概念

**术语完整原则**：保留术语的完整固定搭配。`finite-volume discretization` 不拆成两个 Anchor。`four-dimensional variational assimilation` 整体作为 term；但后文中 "data assimilation" 独立反复出现时，也分别建 Anchor。

### B.3 quantity：数量、数值和度量

**应抽取：**
- 数字、金额、百分比、比例、排名、次数、倍数及单位：`250,000 USD`、`30%`、`three times per day`
- 明确数值范围、上限、下限和阈值：`30% to 40%`、`at least 20 people`
- 明确比分或结果：`5 games to 0`

**粒度规则：**
- `18.4 megawatt-hours`：整体，不拆为 `18.4` + `megawatt-hours`
- `rose by 15%`：只抽 `15%`，不抽 `rose`（谓词属 Event）
- `three million people`：保留计数对象 `people`
- 模糊数量（`many`/`several`）只有在对结论有明确义务时才抽

### B.4 temporal：时间锚点

**应抽取：** 年月日、时刻、明确历史时期、有参照点的相对时间、明确持续期

**不应抽取：** 无参照的 `later`/`soon`/`recently`、纯叙事衔接的 `then`、不能稳定归一的口语时间占位

**消歧**：表达"什么时候/持续多久"→ temporal；普通数量或度量 → quantity。同一表面跨度不重复建。

### B.5 scope：独立范围和适用边界

**应抽取：** 资格/适用边界（`licensed operators only`）、明确比较范围、独立改变适用范围的 only/all/except/at least/at most 结构

**不应抽取：** 孤立的 `only`/`at least`、已完整包含在 quantity 中的边界、无比较对象的 `better`/`more important`

---

## Part C: 类型优先与禁止重复

同一跨度符合多类时，只选最主要核验功能：

```
正式命名对象 → entity
专业方法/技术概念 → term
时间意义 → temporal
数值/单位/金额 → quantity
独立适用边界 → scope
```

禁止给同一信息建立多个重叠 Anchor。允许 Anchor 与 Event 共享证据（评价对象不同）。

---

## Part D: 跨 Segment 的重复概念

不同 segment 中再次出现的同一概念，分别建立独立 Anchor：

```
S1: "Four-dimensional um um variational assimilation" → S1_A1: term
S2: "Data assimilation is not a one-size-fits-all method" → S2_A1: term "data assimilation"
S3: "data assimilation isn't an area he's an expert on" → S3_A2: term "data assimilation"
```

每次出现都应建立 Anchor。后续 SI 评测逐条检查覆盖情况。同一 segment 内机械复述只建一次。

---

## Part E: 字段规范

| 字段 | 说明 |
|------|------|
| `anchor_id` | 段内编号，格式 `{seg_id}_A{n}`：`S1_A1`、`S1_A2`、`S2_A1`。每个 segment 内从 A1 连续编号 |
| `seg_id` | 所属 segment 的 ID |
| `type` | entity / term / quantity / temporal / scope |
| `text` | Anchor 的最小可读表面形式。通常等于 evidence，可去除纯填充但不得删除信息限定或改变词序。不能写入源文没有的同义词或"纠正"源文 |
| `evidence` | segment 文本中的逐字连续子串。保留拼写错误、填充、重复和原始字符，不得翻译/纠错/补词。术语被口语填充打断时，evidence 覆盖真实原文（如 `finite-volume um um discretization`） |
| `importance` | 1=背景, 2=重要, 3=关键（改变身份、数值、结论、行动、风险）。**先完整抽取，再赋 importance。不得因为 importance=1 就不抽。** |

---

## Part F: 口语同传源文处理

- **填充词**（`um`/`uh`/`you know`）不单独建 Anchor
- **重复**（`the the project`）→ 同段内只建一个 Anchor
- **修正**（`re- reform plan`）→ text 为 `reform plan`，evidence 保留残迹
- **自我修正**（`15, no, 50 percent`）→ 保留最终明确值 `50 percent`；未完成修正标 uncertain
- **被填充打断的术语**（`finite-volume um um discretization`）→ 一个完整 term

---

## Part G: Anchor 与 Event 的错误所有权

Anchor 负责槽位值，Event 负责命题框架。Anchor 值错误不能自动让 Event 谓词错误，反之亦然。

```
"The observatory consumed 18.4 MWh"
  → Anchor (quantity): 18.4 MWh
  → Event (action): observatory consumes an energy quantity
```

---

## Part H: 常见失败模式

1. **过抽普通名词**：把每个主语/宾语当 entity
2. **漏抽术语**：只做 NER，忽略方法名和专业概念。反复出现 5 次的 "data assimilation" 只抽一次——严重漏抽
3. **数量拆坏**：`18.4 MWh` 拆成 `18.4` + `MWh`
4. **范围重复**：`at least 20` 同时建 quantity 和 scope
5. **整句当 Anchor**：把完整命题放入 Anchor
6. **孤立谓词当 Anchor**：抽取 `increase`/`announce`
7. **证据清洗**：evidence 不逐字
8. **代词机械抽取**：无 antecedent 的 `it`/`this`
9. **选择性遗漏**：只抽 importance=3
10. **跨 segment 只抽一次**：后两次出现不建 Anchor

---

## Part I: 输出前自检

1. 每条 Anchor 是否通过类型、独立核验、信息义务三问？
2. 是否把普通名词、代词、谓词或整句误当 Anchor？
3. 数值、单位、币种、范围是否形成可比较整体？
4. entity 与 term 是否按"身份 vs 技术概念"正确区分？
5. 每条 evidence 是否逐字存在于对应 segment 中？
6. 同段重复是否去重，不同段出现是否各建 Anchor？
7. 是否先完整抽取再赋 importance？
8. 空 segment 是否输出 `"anchors": []`？

---

## Part J: 输出 JSON

```json
{
  "sample_id": "sample_001",
  "source_anchors": [
    {
      "anchor_id": "S1_A1",
      "seg_id": "S1",
      "type": "term",
      "text": "Four-dimensional variational assimilation",
      "evidence": "four-dimensional um um variational assimilation",
      "importance": 3
    },
    {
      "anchor_id": "S2_A1",
      "seg_id": "S2",
      "type": "term",
      "text": "data assimilation",
      "evidence": "Data assimilation",
      "importance": 3
    },
    {
      "anchor_id": "S2_A2",
      "seg_id": "S2",
      "type": "entity",
      "text": "Dr. Li",
      "evidence": "Dr. Li",
      "importance": 2
    },
    {
      "anchor_id": "S2_A3",
      "seg_id": "S2",
      "type": "term",
      "text": "different observation types",
      "evidence": "different observation types",
      "importance": 2
    },
    {
      "anchor_id": "S2_A4",
      "seg_id": "S2",
      "type": "term",
      "text": "different model domains",
      "evidence": "different model domains",
      "importance": 2
    }
  ]
}
```

没有 Anchor 的 segment 不出现对应项。如果整篇无 Anchor，输出 `"source_anchors": []`。
