# EviSI-Eval v0.6 Anchor Protocol

## 0. 协议定位

Anchor 层只处理能够独立核验的事实槽位。它回答“谁、什么专名、多少、何时、哪个术语、什么范围必须被听众准确获得”，不回答“发生了什么”。动作、状态、判断、言说、否定和情态属于 Event；事件间逻辑属于 Relation。

Anchor 不是传统 NER 的全部名词，也不是关键词摘要。一个短语只有同时满足类型、独立核验和信息义务三个条件才可进入 Anchor Card。

## 1. 三步判定决策树

对每个候选片段 X，严格依次执行：

```text
Q1 类型：X 能否归入 A-ENT/A-QNT/A-TMP/A-TERM/A-SCOPE？
  否 -> 不抽取。
  是 -> Q2。

Q2 独立性：脱离当前谓词后，X 是否仍可被识别、归一或比较？
  否 -> 不抽取；它可能只是 Event 成分。
  是 -> Q3。

Q3 核验义务：若目标译文遗漏或改变 X，听众是否会失去可定位事实？
  否 -> 不抽取；它可能只是普通修饰。
  是 -> 抽取。
```

例：`Company revenue increased by 250,000 US dollars.`

- `increased`：Q1 失败，是谓词，不是 Anchor。
- `revenue increased`：Q2 失败，是不完整 Event。
- `250,000 US dollars`：三问均通过，是 A-QNT。
- 整句：是 Event，不是 Anchor。

## 2. 五类 Anchor 的精确边界

### 2.1 A-ENT：唯一身份或可识别对象

应抽取：

- 人名、明确人物称谓：`Mark`、`President Ursula von der Leyen`；
- 有名称的机构、公司、政府、团队、项目：`World Bank`、`OpenAI`；
- 地点与地理区域：`Geneva`、`European Union`；
- 产品、政策、法规、会议、文件、活动的正式名称：`Ascend 910B`、`Paris Agreement`；
- 当前局部上下文中具有唯一指称、即使没有正式专名也能稳定识别的对象。

不应抽取：

- 没有唯一身份的普通名词：`company`、`system`、`design`、`server`；
- `someone`、`people`、`things` 等泛化对象；
- 无 antecedent 的 `he/it/this/that`；
- 仅因名词在主语位置就把它当实体；
- 技术方法名。`round-robin load balancing` 是 A-TERM，不是 A-ENT。

上下文唯一性必须谨慎：`the company` 只有在当前 segment 内存在唯一且无歧义 antecedent 时才可抽；否则保留在 Event 论元中，不创建 Anchor。

### 2.2 A-QNT：数量、数值和度量整体

应抽取：

- 数字、金额、百分比、比例、排名、次数、倍数；
- 明确数值范围、上限、下限和阈值；
- 数字与币种/计量单位组成的完整核验单位；
- 明确比分或结果：`5 games to 0`；
- 明确频次：`three times per day`。

粒度规则：

- `250,000 US dollars` 整体抽取，不能拆为 `250,000` 与 `US dollars`；
- `30% to 40%` 整体抽取，components 记录 lower/upper/unit；
- `at least 20 people` 可整体作为 A-QNT，components 记录 operator/value/count_unit；
- `three million people` 的 Anchor 应保留核验所需计数对象，不能只留下无法判断对象的数字；
- 谓词不进入 Anchor：`rose by 15%` 只抽数量部分，不抽 `rose`。

模糊数量 `many/several/thousands` 只有在其数量级本身对结论有明确义务时才抽；普通夸张不抽。

### 2.3 A-TMP：时间锚点

应抽取：

- 年月日、时刻、明确历史时期；
- 有参照点的相对时间：`three days after launch`；
- 明确持续期：`for 48 hours`；
- 对行动或结论有约束的频率与期限。

不应抽取：

- 无参照的 `later/soon/recently`；
- 纯叙事衔接的 `then`；
- 不能稳定归一的口语时间占位。

A-TMP 与 A-QNT 消歧：表达“什么时候/持续多久”优先 A-TMP；表达普通数量或度量优先 A-QNT。同一表面跨度只建一个 Anchor，不重复建 A-TMP 和 A-QNT。

### 2.4 A-TERM：术语、方法和领域概念

应抽取：

- 技术、医学、法律、金融、政策、科研术语；
- 缩写、算法名、指标名、方法名、架构名；
- 在领域中具有稳定技术含义的复合概念；
- 过度泛化会产生明确精度损失的术语。

例：`round-robin load balancing`、`monetary tightening`、`point-of-care testing`、`Monte Carlo tree search`。

不应抽取：

- 仅因出现在技术文本中的普通词：`approach`、`system`、`problem`；
- 普通动作的名词化表达，除非形成领域固定概念；
- 可以任意替换而不损失专业含义的日常词。

术语应保留完整固定搭配，不能把 `round-robin load balancing` 拆成 `round-robin` 和 `load balancing` 两个无必要重叠 Anchor。

### 2.5 A-SCOPE：独立范围和适用边界

应抽取：

- 资格或适用对象边界：`children under three`、`low-income households only`；
- 明确比较范围：`among all participating countries`；
- 不与某个 A-QNT 合并、但独立改变适用范围的 only/all/except/at least/at most 等结构；
- 对结论真值有影响的集合限定。

不应抽取：

- 孤立的 `only/at least/more`；
- 已经完整包含在同一个 A-QNT components 中的数量边界；
- 无比较对象的 `better/more important`；
- 普通定语。

### 2.6 类型优先与禁止重复

同一跨度同时看似符合多类时，只选择最主要核验功能：

```text
正式命名对象 -> A-ENT
专业方法/技术概念 -> A-TERM
时间意义 -> A-TMP
数值/单位/金额 -> A-QNT
独立适用边界 -> A-SCOPE
```

禁止为了提高覆盖率而给同一信息建立多个重叠 Anchor。允许 Anchor 与 Event 共享证据，因为二者评价对象不同。

## 3. 表面文本、证据和规范化

### 3.1 evidence_span

- 必须是绑定 segment 中逐字连续片段；
- 保留拼写错误、填充、重复和原始字符；
- 不得翻译、纠错或补词；
- 如果术语被口语填充打断，evidence_span 应覆盖真实连续原文，例如 `round-robin um um load balancing`。

### 3.2 anchor_text

- 表示 Anchor 的最小可读表面形式；
- 通常等于 evidence_span；
- 对被填充词打断的口语短语，可去除纯填充，但不得删除信息限定或改变词序；
- 不能写入源文没有的同义词。

### 3.3 normalized_value

只做不改变事实的轻量规范化：

- `twenty-five million US dollars` -> `25000000 USD`；
- `June 30, 2026` -> `2026-06-30`；
- 大小写、全半角和标准缩写可统一；
- 不把相对时间强行换成未知绝对日期；
- 不把错误或模糊文本“纠正”为模型认为应该存在的事实。

### 3.4 components

components 必须拆出后续客观比较所需的决定性组成。按内容使用，不要求固定全量字段：

```json
{"identity":"Ascend 910B","entity_kind":"product"}
{"value":"250000","currency":"USD"}
{"lower":"30","upper":"40","unit":"percent"}
{"date":"2026-06-30"}
{"duration":"48","unit":"hour"}
{"term":"round-robin load balancing"}
{"scope_operator":"only","scope_set":"children under three"}
```

每个 Source Anchor 至少有一个 component。components 不得包含模型从常识推断、但文本没有表达的值。

## 4. 口语同传源文处理

源文 transcript 可能包含填充、重启、修正和重复：

- `the the project`：同一 segment 内无信息增量只抽一次；
- `re- reform plan`：anchor_text 可为 `reform plan`，evidence_span 保留逐字残留；
- `Round-robin um um load balancing scheme`：作为一个完整 A-TERM，不被填充词拆成多个 Anchor；
- 自我修正 `15, no, 50 percent`：保留最终明确值；如果说话者没有完成修正，标记可核验的多个候选并避免擅自裁决；
- `you know/the thing/that stuff`：不抽；
- 同一句机械复述只抽一次，不同 segment 的再次陈述分别保留 occurrence。

## 5. Anchor 与 Event 的错误所有权

Anchor 负责槽位值，Event 负责命题框架：

| 文本 | Anchor | Event |
|---|---|---|
| `Company received 250,000 USD` | `250,000 USD` | company receives a monetary value |
| `Revenue did not increase by 15%` | `15%` | revenue did not increase |
| `Mark proposed round-robin load balancing` | `Mark`; `round-robin load balancing` | Mark proposes a method |

Anchor 不吸收谓词；Event 仍通过 argument.source_anchor_ids 引用 Anchor。后续 Anchor 值错误不能自动让 Event 谓词错误。

## 6. Importance 确定规则

先完整抽取，再赋 importance。不得因为 importance=1 就不抽。

- `3`：改变身份、数值、结论、行动、风险、资格、法律/医疗/金融含义，或改变关键范围与方向；
- `2`：重要支持事实、专业术语、时间地点条件或约束，缺失明显削弱主旨；
- `1`：背景细节，缺失不改变核心结论、行动或风险。

不得以词长、罕见程度或主观“听起来重要”决定 importance。

## 7. 常见失败模式

1. **过抽普通名词**：把每个主语/宾语都当 A-ENT。
2. **漏抽术语**：只做命名实体识别，忽略方法名和专业概念。
3. **数量拆坏**：把数值与币种/单位拆开，导致无法判断 `USD -> CNY`。
4. **范围重复**：一个 `at least 20` 同时建 A-QNT 和 A-SCOPE。
5. **整句当 Anchor**：把完整行为命题放入 Anchor。
6. **孤立谓词当 Anchor**：抽取 increase/announce/important。
7. **证据清洗**：evidence_span 不再逐字存在。
8. **代词机械抽取**：把 it/this/the thing 作为实体。
9. **规范化补全**：normalized_value 添加源文没有的身份或单位。
10. **选择性遗漏**：只抽 importance=3，忽略合法的低重要度事实。

## 8. 正反例

```text
Source: Revenue rose from 30 million to 45 million US dollars in 2025.
正确：
- A-QNT "30 million"（起点值；components 标出 value）
- A-QNT "45 million US dollars"（终点值与币种）
- A-TMP "2025"
Event 负责 rose/from/to 的变化方向。

Source: The policy applies only to children under three.
正确：A-SCOPE "only to children under three"
错误：A-ENT "children"；A-SCOPE "only"。

Source: Mark discussed round-robin load balancing.
正确：A-ENT "Mark"；A-TERM "round-robin load balancing"
错误：A-ENT "load balancing"；Anchor "discussed"。

Source: I think this is probably better.
若 this 无稳定指向且 better 无比较范围：通常无 Anchor。
Event 仍可表达说话者的不确定评价。
```

## 9. 输出前自检

1. 每项是否通过类型、独立性、核验义务三问？
2. 是否把普通名词、代词、谓词或整句误当 Anchor？
3. 数值、单位、币种、范围是否形成可比较整体？
4. A-ENT 与 A-TERM 是否按身份/技术概念正确区分？
5. A-QNT/A-TMP/A-SCOPE 是否避免同一事实重复？
6. evidence_span 是否逐字存在？
7. components 是否覆盖决定性组成且没有补充常识？
8. 同段重复是否去重，不同段 occurrence 是否保留？
9. 是否先完整抽取再赋 importance？
10. 空结果是否诚实输出空数组？
