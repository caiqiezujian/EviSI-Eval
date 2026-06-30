# EviSI-Eval v0.6 Source-Conditioned Projection Protocol

## 0. 协议定位

Projection 不是自由抽取、不是参考译文相似度匹配，也不是重新评分。Source Card 已经冻结为 Anchor、Event、Relation 三类 Source Items；你的任务是以每个 Source Item 为查询，在目标译文中定位它是否被表达、怎样被表达、哪些组成被保留或冲突。

必须逐一覆盖每个输入 Source Item，顺序与输入一致，一个 Source Item 恰好输出一条 projection。错误译文也要抽取 target span 并标记错误；只有目标译文完全没有相关表达时才是 `missing`。

Projection 的核心判断顺序：

```text
先看 Source Item 的结构和义务
再看目标译文中是否有对应表达
再比较语义组成
最后给 mapping_status、confidence、reason
```

不要先看 Reference 怎么写再要求 SI 复现 Reference。Reference 是辅助线索，不是唯一答案。

## 1. Reference 与 SI 的职责差异

### 1.1 Reference Projection

Reference 是对源文的一个目标语实现，也需要被 Source 约束。Reference Projection 要如实记录它对 Source Item 的表达状态：

- equivalent：等价表达；
- partial：保留核心但有非决定性缺失或弱化；
- contradiction：与 Source 冲突；
- missing：没有表达；
- uncertain：有证据但无法稳定裁决。

Reference 可以帮助识别固定术语、目标语惯用表达和显式硬约束，但不能变成事实权威。

### 1.2 SI Projection

SI Projection 中 Source 是唯一语义权威；Reference 只提供目标语实现线索和已确认硬约束。

必须遵守：

1. SI 与 Reference 不同绝不自动构成错误；
2. SI 找不到 Reference 同款词形绝不自动 missing；
3. Reference 自身 partial/contradiction/missing/uncertain 时，不得用它否定 SI；
4. SI 若用另一种与 Source 等价的表达，必须判 equivalent；
5. 只有硬约束 required=true 时，才检查固定形式或精确组成；
6. Anchor 错误不能重复归 Event，Event 错误也不能重复归 Relation。

## 2. 目标译文切分与搜索范围

每个 target unit 都已由对齐 Agent 绑定到一个或多个 source segment。Projection 时：

- 优先搜索与 Source Item 所在 segment 对齐的 target units；
- 若同传延迟、提前或合并导致错位，可查看前后相邻 target units；
- target_unit_ids 只填写实际承载证据的 units；
- target_spans 必须逐字复制目标译文中的连续片段；
- 多个 target spans 可共同表达一个 Source Item；
- 多个 Source Items 可共享同一 target span，但每条 projection 必须说明自己对应的语义部分。

不得为了让 span 更好看而改写、翻译、规范化或补词。

## 3. Mapping Status 决策树

```text
Q1 目标译文是否存在任何与 Source Item 相关的表达？
  否 -> missing。
  是 -> Q2。

Q2 相关表达是否与 Source Item 的决定性组成发生冲突？
  是 -> contradiction。
  否 -> Q3。

Q3 是否保留所有决定性组成？
  是 -> equivalent。
  否 -> Q4。

Q4 缺失或弱化是否仍保留核心方向，且没有冲突？
  是 -> partial。
  否 -> uncertain。

Q5 是否有证据但无法稳定判断含义、指代、单位或关系？
  是 -> uncertain。
```

Relation 额外有 `not_scored`：当端点 Event 不可用时，Relation 被依赖阻塞，不独立判分。

## 4. Anchor Projection

Anchor Projection 逐个 Source Anchor 比较可核验槽位。

### 4.1 搜索原则

先读取 Source Anchor 的：

- `anchor_type`；
- `anchor_text`；
- `normalized_value`；
- `components`；
- `evidence_span`；
- `importance`；
- hard requirement。

然后在目标译文中寻找同一事实槽位的表达。接受：

- 意译、转写、缩写、目标语惯用译名；
- 数值等价换算，仅在文本明确表达同一单位或可无损规范化时；
- 同一实体的稳定官方译名或广泛通用译名；
- 术语的准确目标语表达。

不接受：

- 只因字形相似就当同一实体；
- 编造别名；
- 把 USD 译成人民币、把百分比译成百分点或反之；
- 把术语泛化成普通词导致专业概念丢失；
- 把 scope 的 only/all/except/under/over 等边界删掉。

### 4.2 component_results

每个 Source Anchor 的 components 必须逐项比较。常用状态：

- `preserved`：该组成被保留；
- `omitted`：目标译文未表达该组成；
- `contradicted`：目标译文表达了冲突值；
- `uncertain`：存在证据但无法稳定判断。

`component_results` 是对冻结 Source components 的逐项核验，不是重新解释 Source：

- component 名称必须与 Source components 完全一致，每项恰好一次；
- source_value 必须复制对应 Source component 的值，不得改写、纠正或重新归一化；
- preserved/contradicted 必须提供目标值和逐字 target_span；
- omitted 的 target_value 与 target_span 必须为 null；
- 目标值错误时仍要抽取其证据并标 contradicted，不能伪装成 missing。

整体 mapping_status：

```text
任一决定性 component contradicted -> contradiction
无冲突但任一决定性 component omitted -> partial 或 missing
所有决定性 component preserved -> equivalent
证据不稳定 -> uncertain
```

若目标译文完全没有相关槽位，mapping_status=`missing`，target_unit_ids 和 target_spans 为空。

### 4.3 示例

```text
Source Anchor: 250,000 US dollars
SI: 25万元
component_results:
- value preserved: 250000
- currency contradicted: USD -> CNY
mapping_status: contradiction

Source Anchor: Ascend 910B
Hard requirement: exact_target_form required_target_form="昇腾910B"
SI: 升腾910B
mapping_status: contradiction
hard_requirement_satisfied: false

Source Anchor: round-robin load balancing
SI: 轮询负载均衡
mapping_status: equivalent
原因：术语完整表达，不要求复现 Reference 字符串。
```

## 5. Event Projection

Event Projection 比较命题框架，不重复评价 Anchor 值。

`target_event_structure` 必须固定包含 core_predicate、predicate_span、arguments、operators、canonical_proposition。operators 必须固定包含 negation、modality、direction、polarity、stance；不得省略字段或另造字段。只要不是 missing，谓词和论元的 surface span 都必须逐字来自所引用 target_units。

### 5.1 必须分别判断三组状态

1. `predicate_status`：核心谓词是否保留；
2. `argument_status`：必要论元角色是否保留；
3. `operator_status`：否定、情态、方向、极性、立场是否保留。

每组状态可用：

- `preserved`
- `omitted`
- `contradicted`
- `uncertain`

### 5.2 Event 判断原则

Event 关注：

- core_predicate 是否同义；
- agent/patient/theme/recipient 等角色是否正确；
- receive/sell、increase/decrease、approve/reject 这类谓词是否反转；
- not/may/must/should/if 等 operator 是否保留；
- stance/attribution 是否保留；
- 问句是否仍是问句，言说是否仍有归属；
- 条件命题是否没有被误译成已发生事实。

Event 不关注：

- Anchor 的数值、币种、时间、术语固定形式是否完全正确；
- 只要不改变谓词框架的同义词选择；
- 由 Anchor 负责的局部拼写或单位错误。

### 5.3 Anchor/Event 错误归属示例

```text
Source Event: company received a monetary value
Source Anchor: 250,000 USD
SI: 公司收到了25万元
Anchor: contradiction（币种错误）
Event: equivalent（receive + agent/value role + gain preserved）

Source Event: company received a monetary value
SI: 公司售货25万美元
Anchor: amount/currency may be preserved
Event: contradiction（receive 被 sell 替换）

Source Event: company did not approve the plan
SI: 公司批准了计划
Event: contradiction（negation lost and meaning reversed）
```

### 5.4 Event mapping_status

```text
完全无相关命题 -> missing
predicate/argument/operator 任一决定性成分 contradicted -> contradiction
无冲突但必要成分 omitted -> partial
三组均 preserved -> equivalent
有目标证据但无法稳定判断 -> uncertain
```

不要用“整体差不多”覆盖谓词、角色、否定、情态或方向错误。

## 6. Relation Projection

Relation Projection 比较 Source Relation 的类型、方向和端点连接。必须先读取 Event projections。

### 6.1 端点依赖

```text
若任一端点 Event mapping_status 为 missing/contradiction/uncertain:
  dependency_status = blocked_by_event
  mapping_status = not_scored
  target_unit_ids = []
  target_spans = []
  reason 说明哪个端点不可用

若全部端点 Event 为 equivalent 或 partial:
  dependency_status = endpoints_available
  继续判断 Relation
```

这样可以避免重复扣分：Event 已经错了，Relation 不再因为同一缺失再次扣分。

### 6.2 Relation 判断原则

目标译文不必使用同一连接词；必须表达相同 relation_type 和方向。

判断重点：

- cause_effect：原因和结果是否保留，方向是否反转；
- condition_consequence：条件是否仍为条件，是否误成已发生事实；
- purpose：目的是否仍是目的，而不是结果；
- concession/contrast：预期违背或对立维度是否保留；
- temporal_sequence/overlap：时序或同时关系是否保留；
- attribution：归属是否保留，是否把报道内容变成无归属事实；
- conclusion：依据与结论方向是否保留。

状态：

- `equivalent`：关系类型和方向保留；
- `partial`：关系弱化但主要连接仍可恢复；
- `contradiction`：关系类型或方向冲突；
- `missing`：端点可用但目标译文没有表达关系；
- `uncertain`：证据不足以稳定判断；
- `not_scored`：端点不可用。

## 7. Hard Requirement

禁止生成 accepted_forms、rejected_forms、allowed_aliases 或 forbidden_aliases 列表。只允许记录少数硬约束：

```json
{
  "required": false,
  "requirement_type": null,
  "required_target_form": null,
  "required_semantics": [],
  "basis": null,
  "reason": ""
}
```

### 7.1 exact_target_form

用于唯一官方目标语形式、产品名、政策名、用户明确提供的固定译名。

- `required_target_form` 是单个字符串；
- 只检查该固定形式是否满足；
- 不扩展同义词表；
- `model_inference` basis 必须触发复核，不能伪装成已验证事实。

### 7.2 exact_value_unit

用于数值、币种、单位、日期、范围等天然精确槽位。

- 比较 normalized components；
- 不要求表面字符串一致；
- 允许无损表达转换；
- 不允许改变单位、币种、倍率、上下界、日期或方向。

### 7.3 required_event_semantics

用于必须严格保持的 Event 结构字段：

- core_predicate；
- negation；
- modality；
- direction；
- polarity；
- stance；
- agent_role/patient_role；
- attribution_scope。

不得把完整参考译文句子设成固定目标形式。

## 8. Reference 辅助限制

SI Projection 使用 Reference 时，只能做三件事：

1. 帮助理解目标语中可能的等价表达；
2. 继承 Reference 阶段已确认的 hard_requirement；
3. 提示可能的 target alignment 范围。

不能做：

- 按 Reference 字符串相似度判 SI 对错；
- 没找到 Reference 的词就判 missing；
- Reference 错误时让 SI 也被判错；
- 把 Reference 的自由译法当唯一合法译法；
- 把 Reference 推断出的 model_inference 硬约束升级为 verified_input。

## 9. Target Additions

完成所有 Source Item projection 后，再扫描目标译文中仍无法归属的明显新增内容，输出到 `target_additions`。

新增内容包括：

- 新增事实、数字、实体、时间；
- 新增因果、条件、结论；
- 新增说话者立场或判断；
- 把不确定内容说成确定事实。

不算新增：

- 目标语必要语法补足；
- 话轮管理；
- 同义重述；
- 纯填充；
- 为了同传流畅添加但不改变事实的连接语。

新增内容不用于修改 Source Item projection；不要为了容纳新增内容而新建 Source Item。

## 10. 禁止行为

1. 输出分数；
2. 改写、合并、删除或新增 Source Item；
3. 编造 target span；
4. 把规范化文本写入 target_spans；
5. 按 Reference 字符串相似度评价 SI；
6. 生成可接受/不可接受译法列表；
7. 用常识补目标译文没有表达的内容；
8. 因 Anchor 值错重复扣 Event；
9. 因 Event 端点错重复扣 Relation；
10. 用模糊 `uncertain` 替代明确的 missing 或 contradiction。

## 11. 输出前自检

1. 是否每个 Source Item 恰好一条 projection？
2. target_spans 是否逐字来自目标译文？
3. mapping_status 是否由 Source 语义决定，而不是 Reference 字符串？
4. Anchor components 是否逐项比较？
5. Event predicate/argument/operator 是否分别判断？
6. Relation 是否先检查端点依赖？
7. hard_requirement 是否只含单一必要约束，而非形式列表？
8. SI 与 Reference 不同但 Source 等价时是否判 equivalent？
9. 错误译文是否仍保留 target span 并标 contradiction？
10. 完全无表达时是否诚实 missing？
