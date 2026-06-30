# EviSI-Eval v0.6 Relation Protocol

## 0. 协议定位

Relation 层只抽取已经存在的 Source Events 之间的语义连接。它回答“两个或多个命题之间是否存在会改变理解的逻辑关系”，不回答实体值是否正确，也不重新抽取事件。

默认没有 Relation。Relation 是稀疏结构，不是相邻句图、话题图、问答图、段落顺序图或摘要大纲。没有充分证据时必须输出空数组；不得为了让图看起来完整而制造关系。

Relation 的作用是为后续同传评估提供可核验义务：

- 译文是否保留了原因和结果的方向；
- 译文是否保留了条件、让步、目的、例外等逻辑限制；
- 译文是否把比较、结论、归因等关系误译成另一种关系；
- 当端点 Event 已经缺失或冲突时，Relation 不重复扣分，而是被标记为 `blocked_by_event/not_scored`。

## 1. Relation 成立的五道门

对每个候选关系，按顺序检查：

```text
Q1 端点门：是否连接至少两个不同的已抽取 Source Event？
  否 -> 不抽取 Relation。
  是 -> Q2。

Q2 方向门：两个端点的角色和方向是否明确？
  否 -> 不抽；只是不清楚的语义联想。
  是 -> Q3。

Q3 信息增量门：该关系是否改变两个 Event 合在一起的解释？
  否 -> 不抽；可能只是并排陈述。
  是 -> Q4。

Q4 证据门：是否存在逐字显式 cue，或唯一且强到 confidence>=0.85 的语义蕴含？
  否 -> 不抽。
  是 -> Q5。

Q5 排除门：是否只是相邻、顺序、问答、话轮转换、同话题或常识推理？
  是 -> 不抽。
  否 -> 抽取 Relation。
```

这五门缺一不可。尤其不能把“看起来有关”当作 Relation；必须能说清楚它是哪一种关系、方向是什么、证据在哪里。

## 2. Relation 与 Event 的边界

Event 是命题端点，Relation 是端点之间的连接。

```text
Source: Sales rose because demand recovered.
Event 1: sales rose
Event 2: demand recovered
Relation: demand recovered causes sales rose
```

不要把 `because demand recovered` 全塞进 Event 1 后就不建 Relation；也不要在没有两个端点 Event 的情况下硬建 Relation。

若一个连接词只改变单个 Event 的内部情态、否定或范围，它属于 Event operator，不是 Relation：

- `may increase`：Event modality；
- `did not approve`：Event negation；
- `only applies to children`：Event/Anchor scope；
- `if approved, the plan will start`：如果 `approved` 与 `plan will start` 都是端点，则是 condition_consequence Relation。

## 3. 17 类 Relation 的严格门槛

### 3.1 cause_effect

文本断言 A 导致、引发、促成、造成 B。显式 cue 包括 `because`, `therefore`, `as a result`, `due to`, `lead to`, `导致`, `因此`, `由于`。

抽取条件：

- A/B 都是 Event；
- 原文把 A 表述为 B 的原因、依据或结果链；
- 方向明确。

不抽：

- A 先发生、B 后发生但没有因果断言；
- 依靠常识补出来的因果；
- `because` 只是口语填充或句子未完成。

### 3.2 condition_consequence

A 是 B 成立、发生或执行的条件。包括真实条件、假设条件、资格条件。

抽取条件：

- 有 `if`, `unless`, `provided that`, `only if`, `as long as`, `如果`, `除非`, `只要` 等条件结构；
- 条件端点和结果端点可恢复；
- 不把条件端点改写成已经发生的事实。

不抽：

- 间接问句中的 `if/whether`；
- `if any` 这类局部限定；
- 单个 Event 内的条件 operator 没有独立端点。

### 3.3 purpose

A 是为了实现 B，B 是 A 的目的。

抽取条件：

- 目的端点不是已经断言发生的结果，而是行动目标；
- cue 包括 `to`, `in order to`, `so that`, `为了`, `以便`；
- A/B 方向明确：action -> intended goal。

不抽：

- 普通不定式补足语；
- 实际结果误当目的；
- 目的对象没有形成 Event。

### 3.4 concession

尽管 A 成立，B 仍成立，预期被违背。

抽取条件：

- cue 包括 `although`, `despite`, `even though`, `nevertheless`, `尽管`, `即使`, `仍然`；
- A 与 B 之间存在“本应影响但没有阻止”的关系。

不抽：

- 普通 contrast；
- 只是补充背景，没有违背预期。

### 3.5 contrast

A 与 B 在同一比较维度上明确对立。

抽取条件：

- 有共同维度，例如成本、速度、风险、态度、结果；
- cue 包括 `but`, `whereas`, `while`, `however`, `相比之下`, `但是`, `而`；
- 对立方向可说明。

不抽：

- 两个内容不同的句子；
- 话题转换；
- `but` 只是口语转折，没有语义对立。

### 3.6 temporal_sequence

文本断言 A 先于 B、B 后于 A 或按顺序发生。

抽取条件：

- 有明确时序 cue：`before`, `after`, `then`, `first...then`, `随后`, `之前`, `之后`；
- cue 表达现实事件顺序，而不是叙述顺序。

不抽：

- 文本先写 A 后写 B；
- 演讲者先提 A 后提 B；
- 每个相邻 Event 自动建 sequence。

### 3.7 temporal_overlap

A 与 B 同时、重叠或在同一时间窗口内发生。

抽取条件：

- cue 包括 `while`, `during`, `at the same time`, `meanwhile`, `同时`, `期间`；
- overlap 改变事件理解。

不抽：

- 同一段落出现；
- 共同背景时间已由 Anchor 表示且没有事件间重叠义务。

### 3.8 conjunction

A 与 B 被明确组合为同一决策、清单、方案或并列义务。

抽取条件：

- 组合关系本身有信息价值，例如“同时执行 A 和 B”“两项措施都必须完成”；
- 不是普通连续陈述；
- 不替代独立 Event 的抽取。

不抽：

- 每个 `and` 都建 conjunction；
- 同一句里两个动作已各自独立，组合不改变理解。

### 3.9 progression

B 在同一维度上比 A 更进一步、升级、递进或扩展。

抽取条件：

- cue 包括 `furthermore`, `more importantly`, `not only...but also`, `进一步`, `更重要的是`, `不仅...还`；
- A/B 共享维度且 B 明确推进。

不抽：

- 普通补充；
- 只因 B 写在后面就认为递进。

### 3.10 similarity

A 与 B 被文本明确表述为相似、相同或可类比。

抽取条件：

- 有共同维度；
- cue 包括 `similarly`, `like`, `as with`, `类似`, `同样`；
- 不是模型自己觉得类似。

### 3.11 difference

A 与 B 被明确表述为不同、区分或不等同。

抽取条件：

- 有共同维度；
- cue 包括 `different from`, `unlike`, `distinguish`, `不同于`, `区别在于`；
- 方向和比较对象明确。

### 3.12 degree

A 与 B 存在程度、强弱、大小、优先级或排序关系。

抽取条件：

- 有明确比较维度；
- cue 包括 `more than`, `less than`, `higher than`, `at least as`, `比...更`, `高于`, `低于`；
- 该比较不是单个 A-QNT Anchor 已经完全覆盖的数值槽位。

不抽：

- `more` 没有比较对象；
- 纯数值大小由 Anchor 处理，无 Event 间关系。

### 3.13 elaboration

B 对 A 进行具体化、解释、重述或展开。

抽取条件：

- B 与 A 是同一命题或同一对象的更具体版本；
- cue 包括 `that is`, `in other words`, `namely`, `也就是说`, `换句话说`, `具体来说`；
- B 不是一个新的独立话题。

不抽：

- 话题延续；
- B 只是同段落下一句。

### 3.14 attribution

某命题明确归属于来源、说话者、研究、报告或机构。

抽取条件：

- 一个端点是言说/报告/判断来源 Event，另一个端点是被归属内容；
- 归属改变命题现实性或责任；
- cue 包括 `said`, `according to`, `reported`, `claimed`, `表示`, `根据`, `报告称`。

不抽：

- Event 已经完整记录 `Mark said X` 且内容不另建 Event；
- 归属来源只是 Anchor，没有形成 Event 端点。

### 3.15 exemplification

B 是 A 所述类别、原则、现象或论点的例子。

抽取条件：

- cue 包括 `for example`, `such as`, `including`, `例如`, `比如`, `包括`；
- A 是类/规则/观点，B 是实例。

不抽：

- 普通列举；
- `including` 只是 A-SCOPE 或 A-ENT 内部组成。

### 3.16 exception

B 被明确排除在 A 的规则、范围或结论之外。

抽取条件：

- cue 包括 `except`, `except for`, `other than`, `unless`, `除...之外`, `不包括`；
- 排除对象形成可核验端点或范围义务。

不抽：

- 普通否定；
- 单个 Anchor scope 已足够，不存在 Event 间连接。

### 3.17 conclusion

B 是从 A 推出的结论、建议、决定或总结。

抽取条件：

- cue 包括 `therefore`, `so`, `in conclusion`, `we conclude`, `因此`, `所以`, `综上`；
- B 明确依赖 A 作为推理依据；
- 方向 A -> B 明确。

不抽：

- 最后一句自动当结论；
- 说话者换话题；
- 常识上可推但文本未推。

## 4. 强制假阳性排除清单

以下情况即使有连接词，也通常不抽 Relation：

1. 问句后出现回答；
2. 说话人轮次转换；
3. 两句讨论同一主题但没有逻辑连接；
4. A 先写、B 后写；
5. `and/so/then/but` 只是口语组织；
6. 两句内容不同但没有共同比较维度；
7. 为每个相邻 Event 创建 temporal_sequence 或 elaboration；
8. A->B、B->C 成立后自动添加 A->C；
9. 把 Anchor 的数值比较误建为 Event Relation；
10. 把 Event 内部否定、情态、范围误建为 Relation。

## 5. 证据与字段规范

每个 Relation 必须输出：

- `source_relation_id`：从 SR1 连续编号；
- `segment_ids`：只列提供该关系证据的 source segment，按文本顺序排列，可非连续；
- `relation_type`：必须为 17 类之一；
- `relation_basis`：`explicit_cue` 或 `strong_semantic_entailment`；
- `relation_cue`：显式 cue 时复制逐字 cue；强蕴含时为空字符串；
- `confidence`：0-1；`strong_semantic_entailment` 必须 >=0.85，否则不抽；
- `relation_text`：用端点 ID 和方向简明描述，例如 `SE2 causes SE1`；
- `relation_meaning`：自然语言说明关系含义，不增添文本没有的推理；
- `evidence_spans`：覆盖端点和 cue 的逐字证据，可多段；
- `related_source_event_ids`：至少两个不同 Event ID，只列实际端点；
- `importance`：1/2/3。

### relation_basis 的使用

`explicit_cue`：文本中有可复制的连接词、结构或标点信号。relation_cue 必须逐字来自原文。

`strong_semantic_entailment`：没有显式 cue，但原文结构唯一地表达关系。例如“目标是降低延迟”可以支持 purpose；“A, not B”可以支持 contrast/difference。使用时必须更谨慎，confidence 低于 0.85 不抽。

## 6. Importance 规则

- `3`：关系改变结论、责任、因果、条件、行动、风险、法律/医疗/金融含义；
- `2`：关系是重要解释、约束、比较或归因，缺失会明显削弱理解；
- `1`：背景性连接，缺失不改变核心行动或结论。

不要因为 cue 明显就给高分；importance 取决于关系对意义的影响。

## 7. Relation Projection 与防重复扣分

Projection 阶段必须先检查端点 Event projections：

```text
任一端点 Event 为 missing/contradiction/uncertain:
  dependency_status = blocked_by_event
  mapping_status = not_scored
  Relation 不再扣分

所有端点 Event 为 equivalent 或 partial:
  dependency_status = endpoints_available
  再判断目标译文是否保留 relation_type、方向和必要 cue/语义
```

Relation 不要求译文使用同一连接词。只要目标译文清楚表达相同关系和方向，即可 equivalent。Reference 中没有显式 Relation 不能自动否定 SI Relation；SI 是否正确仍回到 Source Relation。

## 8. 正反例

```text
Source: Demand recovered, so sales rose.
Events: SE1=demand recovered; SE2=sales rose
正确 Relation: cause_effect, SE1 causes SE2, cue="so"

Source: The system is fast, and the interface is simple.
若只是两个属性并列，通常无 Relation。
若原文说 "both requirements must be met"，才可能有 conjunction。

Source: He asked whether the report was ready. She said yes.
不要抽 question-answer Relation。问句和回答是各自 Event。

Source: The model is smaller but more accurate.
若 smaller 与 more accurate 是两个 Event/State，且共同维度是模型属性对立，可抽 contrast。
不要仅因 `but` 出现就抽；必须说明对立维度。

Source: Programs simulate thousands of games, such as Go and chess matches.
若 Go/chess 只是 Anchor 或范围，不一定形成 exemplification Relation。
只有当 A 是事件/原则、B 是该事件/原则的实例 Event 时才抽。
```

## 9. 输出前自检

1. 是否默认从空关系开始，而不是从相邻 Event 自动连边？
2. 每条 Relation 是否至少连接两个已有 Source Event？
3. relation_type 是否属于 17 类且门槛满足？
4. 方向是否能用 `SEi -> SEj` 清楚说明？
5. relation_cue 是否逐字存在，或 strong entailment 是否真的唯一且 confidence>=0.85？
6. 是否排除了问答、话轮、同话题、普通顺序和常识推理？
7. 是否没有把 Event 内部 operator 或 Anchor 数值槽位误当 Relation？
8. evidence_spans 是否逐字存在？
9. related_source_event_ids 是否只列端点且没有编造 ID？
10. 空结果是否诚实输出 `source_relations: []`？
