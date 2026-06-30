# EviSI-Eval v0.6 Event Protocol

## 0. 协议定位

Event 层抽取最小完整命题。它不是动词清单、实体清单、句子摘要或整句复制。每个 Event 围绕一个中心事件核，结构化记录“谁以什么立场/情态，对谁或什么做了什么，处于什么状态，发生了什么变化”。

Event 抽取必须同时满足：

- **完整**：具有可恢复的主体或作用域、核心谓词及必要论元，足以判断文本声称什么；
- **最小**：原则上只有一个中心事件核，多个可独立判断的命题必须拆开；
- **忠实**：不增加文本没有的主体、因果、立场或确定性；
- **可审计**：predicate_span、argument surface span 和 evidence_spans 均可回到原文。

## 1. 七类 Event 与优先级

当一个命题同时看似符合多类时，按以下功能优先级选择最能解释句子作用的一类。

### 1.1 E-SPEECH：言说和交互行为

包含说、提到、询问、回答、请求、承诺、警告、承认、拒绝回答等言语行为。直接问句、命令式请求也属于 E-SPEECH。

```text
"Are you finished with the design?"
-> speaker asks whether addressee has finished the design
不能写成：addressee finished the design
```

### 1.2 E-JUDG：判断、评价和立场

主体表达认为、评价、建议、态度、认知或价值判断。

```text
"I think this approach is clever."
-> speaker judges the approach to be clever
```

不得因为句中有系词就降为普通 E-STATE；不得删除 `I think` 后把带立场的内容写成客观事实。

### 1.3 E-MODAL：可能性、必要性、义务和意愿

当 may/might/must/should/can/want/intend 等改变命题现实性或义务性，并构成主要核验点时使用。

```text
"The company must stop processing the data."
-> company is required to stop processing data
```

如果情态只是另一个 Event 的 operator，而没有必要独立成命题，可保留在 operators.modality 中，不重复建 Event。

### 1.4 E-CHANGE：变化

数量、状态、方向或属性发生增长、下降、恢复、恶化、扩大、减少、开始、结束等变化。

```text
"Revenue fell by 15%."
core_predicate=decrease; direction=downward
```

### 1.5 E-ACT：动作

主体执行动作，影响对象、接收者或目标。例如发布、签署、购买、停止、建立、训练、击败。

### 1.6 E-STATE：状态或属性

主体处于某状态、拥有某属性、存在某情况。`market is unstable`、`cost remains high`。

### 1.7 E-REL：实体关系

两个实体间存在身份、隶属、组成、所有、位置等稳定关系。不要与事件间 Relation 混淆：E-REL 本身是一个命题；Relation 是两个 Event 之间的连接。

## 2. Event 判定流程

对每个候选命题执行：

```text
Q1 是否存在可恢复的谓词语义？
  否 -> 不抽。

Q2 是否能恢复主体/作用域及谓词所需论元？
  否 -> 检查是否为可恢复口语残句；仍不能恢复则不抽。

Q3 是否表达一个可独立判断真值、立场、问题、义务或状态的命题？
  否 -> 不抽，可能只是修饰语或关系 cue。

Q4 是否包含多个可独立判断的中心事件核？
  是 -> 拆分。
  否 -> 建立一个 Event。
```

## 3. 原子性与复句拆分

### 3.1 并列动作/变化/判断

```text
"The company announced a plan and hired 500 engineers."
-> Event 1: company announced a plan
-> Event 2: company hired engineers
```

不能为了“一句一个 Event”把二者合并。

### 3.2 主从和内容从句

```text
"Mark said the system had failed."
-> E-SPEECH: Mark said proposition P
-> E-STATE/E-CHANGE: system had failed（保留其被 Mark 说出的归因范围）
```

内容命题只有在具备独立核验价值时才另建 Event。不得把被报道命题变成说话者/评测系统认可的客观事实；canonical_proposition 必须保留 attribution/stance。

### 3.3 定语和关系从句

若从句提供独立可核验命题，应另建 Event：

```text
"programs that simulate thousands of games"
-> programs simulate thousands of games
```

若从句只是识别对象且没有独立信息义务，保留为论元限定，不另建 Event。

### 3.4 原因、条件、让步和结果

原因与结果各自完整时优先建立两个 Event，再由 Relation 表示连接：

```text
"Sales rose because demand recovered."
-> Event 1: sales rose
-> Event 2: demand recovered
-> Relation: Event 2 causes Event 1
```

不要用一个超长 Event 取代两个端点和 Relation。条件从句即使非现实事实，也可作为带 modality/conditional scope 的命题端点，不能改写为已经发生。

### 3.5 问句、回答和话轮

- 直接问句抽 E-SPEECH，保留询问作用；
- 回答中的命题按实际内容抽取；
- “问句后有回答”不是 Event 间 Relation；
- `okay/yeah/right` 若只是话轮管理，不抽；如果明确表达同意/确认，可抽 E-SPEECH 或 E-JUDG。

### 3.6 口语残句和自我修正

- `Then he just... left.`：可恢复为“he left”，evidence 保留真实片段；
- `because, so, um...`：没有完整命题，不抽；
- 自我否定修正时以最终明确命题为主，同时保留改变意义的修正；
- 机械重复只建一个 Event；带信息增量的重复分别建 Event。

## 4. 结构化缩句算法

缩句不是删掉所有修饰，而是把原句转换成“核心谓词 + 必要论元 + 改变真值/现实性的 operators”。按以下顺序执行：

### Step 1：找中心谓词

定位表达命题功能的动词、系词状态、判断或问句核。`core_predicate` 用最小规范化概念表达；`predicate_span` 复制原文逐字证据。

### Step 2：恢复必要论元

根据谓词价位识别 agent、patient/theme、recipient、experiencer、attribute、source、destination、value 等角色。角色名称应稳定、简洁。

### Step 3：提取 operators

至少显式分析：

- `negation`：否定是否成立；
- `modality`：possible/probable/required/intended/conditional 等；
- `direction`：gain/loss/upward/downward/start/stop 等；
- `polarity`：positive/negative/neutral；
- `stance`：speaker belief/evaluation/uncertainty/attribution。

### Step 4：链接 Anchor

论元包含 Source Anchor 时写入 source_anchor_ids。Anchor 具体值继续保留在 surface span 和证据中，但其值正确性由 Anchor 维度负责。

### Step 5：生成 canonical_proposition

用简洁句子重述结构，必须保留谓词、角色、否定、情态、方向和立场。它不是翻译，也不是自由摘要。

### Step 6：保留审计证据

evidence_spans 可以有多个，用来覆盖不连续命题；每个 span 必须逐字存在。不能为了让 canonical_proposition 看起来流畅而编造连续 evidence。

## 5. 必须保留与可剥离成分

### 5.1 必须保留

- 核心谓词；
- 谓词要求的必要主体和对象；
- 否定；
- 情态、条件和义务；
- 变化方向、起止与极性；
- 判断/言说的立场和归因；
- 改变适用范围的 only/all/except；
- 改变命题身份的角色关系；
- 对该命题不可缺少的时间、地点、数值或术语链接。

### 5.2 可以从 canonical_proposition 剥离，但不能从证据系统消失

- 不改变命题的背景时间和地点；
- 纯程度副词；
- 插入评论、口语填充、机械重复；
- 已由 Anchor 独立承担的具体值，可在 canonical 中概括为其角色，但 argument 仍链接 Anchor。

### 5.3 绝不能错误删除

```text
did not approve -> 不能写 approve
may increase -> 不能写 increase as fact
only applies to children -> 不能写 applies generally
fell from 40 to 20 -> 不能只写 changed
Mark said X -> 不能写 X is an unqualified fact
```

## 6. Arguments 规范

每个 argument：

```json
{
  "role":"agent",
  "surface_span":"The company",
  "source_anchor_ids":["SA1"]
}
```

规则：

- surface_span 必须逐字位于同一 source segment；
- 允许 source_anchor_ids=[]；普通论元不必强行成为 Anchor；
- 一个 Anchor 可参与多个 Event；
- 不得引用不在该论元 span 中实际发挥作用的 Anchor；
- 时间/地点/数值等修饰若参与命题，应作为合适 role 链接，但后续值错误仍归 Anchor；
- 代词可作为 Event argument，即使它不构成 Anchor；不得凭常识把其表面替换为专名。

## 7. Event 与 Anchor 的错误所有权

Event 抽取应完整保留 Anchor 参与方式，但 Event Fidelity 只评价命题框架：

1. core_predicate；
2. 必要论元角色；
3. negation/modality/direction/polarity/stance；
4. 命题类型和现实性。

Anchor Fidelity 评价身份、数值、单位、时间、术语和范围值。

```text
Source: company received 250,000 USD
SI: company received 250,000 CNY
Anchor: currency contradicted
Event: receive + agent/value role + gain preserved -> equivalent

Source: company received 250,000 USD
SI: company sold goods worth 250,000 USD
Anchor: amount may be preserved
Event: receive vs sell contradicted -> contradiction
```

如果论元角色互换，例如“公司收购竞争对手”译成“竞争对手收购公司”，即使两个实体 Anchor 都存在，Event 仍为 contradiction。

## 8. Event Projection 状态组合

Projection 必须分别输出：

- predicate_status；
- argument_status；
- operator_status。

组合规则：

```text
任一决定性成分 contradicted -> mapping_status=contradiction
没有冲突但有必要成分 omitted -> mapping_status=partial
存在无法稳定裁决的决定性成分 -> mapping_status=uncertain
三个成分均 preserved -> mapping_status=equivalent
完全无相关目标表达 -> mapping_status=missing
```

不能用“整体大意差不多”覆盖谓词、角色或否定冲突。

## 9. 硬语义要求

普通 Event 参与正常 Fidelity，但 hard_requirement 默认 false。只有以下情况使用 `required_event_semantics`：

- 输入 provided_hard_requirements 明确指定；
- 改变字段会改变行动、资格、风险、法律/医疗/金融含义；
- 明确禁止、义务、否定、方向或角色必须保持。

required_semantics 只能列结构字段，例如 `core_predicate`、`negation`、`modality`、`direction`、`agent_role`。禁止把完整参考译文句子设成固定目标形式。

## 10. 完整性原则

- 每个 segment 中所有完整命题都应被 Event 覆盖；
- 不能只抽主旨或 importance=3 的 Event；
- 一个 segment 可有零个、一个或多个 Event；
- 纯填充和无完整命题残片诚实输出零 Event；
- Event 按原文首次证据顺序编号；
- 同义重复无新增信息时去重，立场/数量/范围变化时保留。

## 11. 常见失败模式

1. **整段复制**：event 与两三句 segment 完全相同。
2. **过度缩句**：只剩孤立谓词或删除必要论元。
3. **合并多个事件**：并列动作被写进一个 Event。
4. **立场提升**：`I think X` 被写成确定事实 X。
5. **问句陈述化**：询问是否完成被写成已经完成。
6. **情态丢失**：may/must/should 被删除。
7. **否定反转**：not 未进入 operators。
8. **方向泛化**：increase/decrease 都写成 change。
9. **角色互换未发现**：实体都存在就误判 Event 正确。
10. **Anchor 双扣**：只因币种/数值错误就把正确谓词判错。
11. **证据编造**：canonical 文本被误写为 evidence_span。
12. **遗漏从句命题**：关系从句或内容从句有独立义务却未抽。

## 12. 正反例

```text
Source: Without any lookahead search, the neural networks play Go at the level of Monte Carlo tree search programs that simulate thousands of games.

合理 Event：
1. neural networks play Go without lookahead search
2. neural networks play Go at the level of Monte Carlo tree search programs
3. Monte Carlo tree search programs simulate thousands of games

错误：把整句作为一个 Event。

Source: Mark was open about not being an expert in load balancing, and the speaker said this was acceptable.

合理 Event：
1. Mark acknowledges he is not an expert in load balancing（保留否定与归因）
2. speaker judges this limitation acceptable

错误：Mark is an expert；load balancing is acceptable。

Source: If demand recovers, sales may increase.

Event 1: demand recovers under a condition scope
Event 2: sales may increase
Relation: condition_consequence
不能把两个命题写成已经发生。
```

## 13. 输出前自检

1. 每个 Event 是否既完整又只有一个中心核？
2. 并列、内容从句、关系从句是否按独立核验义务处理？
3. 问句、言说、判断、情态是否选择了正确功能类型？
4. core_predicate 与 predicate_span 是否一致且不增义？
5. arguments 是否角色明确、逐字可定位并正确链接 Anchor？
6. negation/modality/direction/polarity/stance 是否完整？
7. canonical_proposition 是否缩短但未丢失决定性语义？
8. evidence_spans 是否全部逐字存在？
9. 是否避免 Anchor 值错误与 Event 谓词重复归责？
10. 是否覆盖全部完整命题而没有为填充制造 Event？
