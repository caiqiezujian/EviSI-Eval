# EviSI-Eval v0.5 完整评估流程与计分规范

> 版本：0.5.0 | 协议：evisi_eval_v0.5 | 2026-06-30

---

## 目录

1. [系统总览](#1-系统总览)
2. [Phase 1：构建冻结源证据卡](#2-phase-1构建冻结源证据卡sourcecardagent)
3. [Phase 2：对齐](#3-phase-2对齐alignmentagent)
4. [Phase 3：目标侧盲证据抽取](#4-phase-3目标侧盲证据抽取targetevidenceagent)
5. [Phase 4：流利度评估](#5-phase-4流利度评估fluencyagent)
6. [Phase 5：SI 表达评估](#6-phase-5si-表达评估siexpressionagent)
7. [Phase 6：组装目标评估卡](#7-phase-6组装目标评估卡target-eval-card)
8. [Phase 7：首轮判定](#8-phase-7首轮判定primaryjudgeagent)
9. [Phase 8：独立复核](#9-phase-8独立复核revieweragent)
10. [Phase 9：分歧检测与裁决](#10-phase-9分歧检测与裁决adjudicatoragent)
11. [Phase 10：判定合并](#11-phase-10判定合并merge-judgements)
12. [Phase 11：确定性计分](#12-phase-11确定性计分calculate_scores)
13. [Phase 12：叙述性总结](#13-phase-12叙述性总结summaryagent)
14. [Runner 执行机制](#14-runner-执行机制)
15. [输出产物](#15-输出产物)
16. [Metrics 聚合](#16-metrics-聚合)

---

## 1. 系统总览

EviSI-Eval 是一个 LLM Agent 驱动的同声传译最终译文质量评估系统。输入为一个源文样本 + 多个同传系统译文，经过 **10 个 Agent 组成的串行流水线**，输出每个（样本, 系统）的五维得分和完整证据链。

### 1.1 核心设计约束

- **LLM 只做语义判断**（抽取、判定、总结），不参与计算。
- **代码只做编排、结构校验和确定性计算**，不判断翻译正确性。
- **源证据卡冻结**：每个样本的源语义分析只执行一次，所有系统共享同一基准。
- **目标侧盲抽取**：目标证据抽取 Agent 看不到源文，防止被诱导。
- **双模型复核**：主判和复核各自独立判定，分歧或低置信度触发第三方裁决。
- **参考译文永不传入任何 Agent**。

### 1.2 五维评分

| 维度 | 权重 | 测量对象 | 计分方式 |
|---|---|---|---|
| Anchor Fidelity | 30% | 实体、数字、时间、术语、范围的事实准确性 | 加权正确率（importance 1/2/3） |
| Event Fidelity | 25% | 动作、状态、变化、判断、言说、情态的命题传达率 | 加权正确率 |
| Relation Fidelity | 20% | 因果、条件、转折、时序等逻辑关系的传达率 | 加权正确率 |
| Fluency | 15% | 目标语言本身的通顺度与可理解性 | 100 − 问题扣分 |
| SI Expression | 10% | 同传特有的表达效率与组织负担 | 100 − 问题扣分 |

### 1.3 完整调用拓扑

```
run_pipeline (pipeline.py)
  │
  ├─ SourceCardAgent.build(sample)          → source_card (每个样本一次，冻结)
  │
  └─ 对每个 (sample, system) pair：
       EvaluationAgentLoop.run(source_card, output)
         │
         ├─ [1] AlignmentAgent.align()          → eval_units
         ├─ [2] TargetEvidenceAgent.analyze()   → target anchor/event/relation
         ├─ [3] FluencyAgent.evaluate()         → fluency_issues + assessment
         ├─ [4] SIExpressionAgent.evaluate()    → si_expression_issues + assessment
         ├─ [5] 组装 target_eval_card
         ├─ [6] PrimaryJudgeAgent.judge()       → anchor/event/relation judgements
         ├─ [7] ReviewerAgent.judge()           → 独立复核 judgements
         ├─ [8] _build_disagreement_cases()      → 比较主判和复核，找分歧
         ├─ [9] AdjudicatorAgent.adjudicate()    → 裁决（仅当有分歧时调用）
         ├─ [10] _merge_judgements()             → 合并为最终判定
         ├─ [11] calculate_scores()              → Python 确定性五维计分
         └─ [12] SummaryAgent.summarize()        → 叙述性总结
```

---

## 2. Phase 1：构建冻结源证据卡（SourceCardAgent）

### 2.1 调用

```python
SourceCardAgent(primary_client).build(sample)
# 输入: {"sample_id", "source_text", "src_lang", "tgt_lang", "domain"}
```

**信息隔离**：只看 `source_text`，看不到任何系统译文或参考译文。

### 2.2 LLM 任务

调用 prompt `source_evidence_agent`（自动前置 Shared Semantic Extraction Protocol），要求 LLM 完成四项任务：

#### 任务一：无损切分（Source Units）

- 将 `source_text` 按句子或自然话语段切分为 `source_units`
- 不做句内细切（定语从句、插入语、后置修饰、长宾语等不拆开）
- **无损约束**：所有 `source_unit` 按顺序拼接 == `source_text`（由 `validate_source_units()` 强制校验）
- 保留原始标点、空格、换行、口语填充、重复、残句
- ID 从 S1 连续编号

#### 任务二：Anchor 抽取

Anchor 是**可独立核验的事实信息点**，5 大类 13 子类：

| 大类 | 编码 | 包含子类 |
|---|---|---|
| 实体 | A-ENT | 人名/人物称谓、机构/组织/公司、地点/地理区域、产品/政策/法规/活动/文件名 |
| 量化 | A-QNT | 数字/金额/比例/排名、度量单位+数量、范围/规模/序数/频率 |
| 时间 | A-TMP | 绝对时间、有明确参照的相对时间/时段/频率 |
| 术语 | A-TERM | 专业术语、缩写、行业概念（命名技术方案属此类，不属 A-ENT） |
| 限定 | A-SCOPE | 限定对象/群体/类别、边界限定语（至少/超过/约）、比较级/最高级限定 |

每个候选片段通过**三步决策树**判定：

```
问题 1：X 是否属于五类之一？             → 否 → 不是 Anchor
问题 2：X 能否脱离谓词独立验证？         → 否 → 不是 Anchor（可能是 Event 成分）
问题 3：X 是否带来无法回避的核验义务？   → 否 → 不是 Anchor（可能是修饰成分）
                                          → 是 → 抽取
```

Anchor 与 Event 不互斥：同一个文本片段可以既是 Anchor（独立事实槽位）又是 Event 的一部分（命题语义成分），两者分别抽取，evidence_span 可以重叠。

每个 Anchor 字段：
- `source_unit_id`：归属的源单元
- `source_anchor_id`：SA1、SA2、SA3... 连续编号
- `anchor_type`：五类之一
- `anchor_text`：表面文本
- `normalized_meaning`：轻度标准化（可数字标准化、拼写规范化，**禁止**添加新信息、禁止纠正拼写错误、禁止改变数值/单位）
- `evidence_span`：在对应 source_unit 中**逐字**存在的连续片段（不得清理填充词）
- `importance`：1/2/3

#### 任务三：Event 抽取

Event 是**最小完整命题语义单位**，7 种类型（按优先级从高到低）：

| 优先级 | 编码 | 类型 | 判定关键 |
|---|---|---|---|
| 1 | E-SPEECH | 言说事件 | 是否在执行言语行为（说、问、请求、承诺）？ |
| 2 | E-JUDG | 判断事件 | 是否在表达主观认为/评价/态度？ |
| 3 | E-MODAL | 情态事件 | 情态是否改变命题的现实性/义务性？ |
| 4 | E-CHANGE | 变化事件 | 属性/状态是否发生了变化？ |
| 5 | E-ACT | 动作事件 | 主体是否执行了动作？ |
| 6 | E-STATE | 状态事件 | 主体是否处于某种状态/具有属性？ |
| 7 | E-REL | 关系事件 | 两实体间是否有结构关系？ |

边界规则：并列拆分、主从可拆（从句有独立命题时）、残句按可恢复性处理、同一单元多事件分别抽取。Completeness 原则要求覆盖单元中所有命题。

每个 Event 字段：`source_unit_id`、`source_event_id`(SE1/SE2...)、`event_type`、`event_text`、`canonical_meaning`（保留否定/方向/情态/立场）、`evidence_span`（逐字）、`importance`(1/2/3)。

#### 任务四：Relation 抽取

Relation 是事件间的逻辑关系，17 种类型：`cause_effect`、`condition_consequence`、`purpose`、`concession`、`contrast`、`temporal_sequence`、`temporal_overlap`、`conjunction`、`progression`、`similarity`、`difference`、`degree`、`elaboration`、`attribution`、`exemplification`、`exception`、`conclusion`。

**默认没有 Relation。** Relation 是稀疏的意义结构。没有充分证据时输出空数组。

新增字段：
- `relation_basis`：`explicit_cue`（有逐字连接词）或 `strong_semantic_entailment`（强语义蕴含）
- `relation_cue`：explicit_cue 时逐字复制原文 cue；implicit 时空字符串
- `confidence`：0–1，strong_semantic_entailment **必须 ≥ 0.85**

强制排除：相邻出现、问答对话、话题延续、口语 `and`/`so`/`then` 作为组织词时、内容不同但没有对立比较维度时。

每个 Relation 字段：`source_relation_id`(SR1/SR2...)、`relation_type`、`relation_basis`、`relation_cue`、`confidence`、`source_unit_ids`、`relation_text`、`relation_meaning`、`evidence_spans`、`related_source_event_ids`、`importance`。

### 2.3 输出

```json
{
  "sample_id": "...",
  "source_text": "...",
  "source_units": [{ "source_unit_id": "S1", "source_unit": "..." }],
  "source_anchors": [{ "source_unit_id": "S1", "source_anchor_id": "SA1", ... }],
  "source_events": [{ "source_unit_id": "S1", "source_event_id": "SE1", ... }],
  "source_relations": [{ "source_relation_id": "SR1", ... }],
  "metadata": {
    "protocol_version": "evisi_eval_v0.5",
    "frozen_before_system_evaluation": true,
    "source_card_hash": "<sha256 of all fields except metadata>",
    "prompt_hashes": { ... }
  }
}
```

**source_card_hash** 由 `_artifact_hash()` 计算：对除 `metadata` 外的所有字段做 `json.dumps(sort_keys=True)` 后 SHA-256。所有后续系统共享同一份冻结 source_card。

---

## 3. Phase 2：对齐（AlignmentAgent）

### 3.1 调用

```python
AlignmentAgent(primary_client).align(source_card, output)
# 输入: source_units + si_translation（译文全文）
```

**信息隔离**：AlignmentAgent 是**唯一同时看到源文和译文的 Agent**。此后所有目标侧 Agent 只看译文。

### 3.2 任务

将译文无损切分为 `eval_units`，每个 eval_unit 绑定零个或多个 `source_unit_ids`，标注对齐状态：

| alignment_status | source_unit_ids | target_unit | 含义 |
|---|---|---|---|
| `aligned` | 有 | 有 | 正常对齐 |
| `source_omitted` | 有 | 空 | 源有此内容、目标缺失 |
| `target_addition` | 空 | 有 | 目标多出、源无对应 |
| `uncertain` | 可为空 | 可为空 | 不确定对齐关系 |

### 3.3 验证约束

`validate_alignment_artifact()` 强制：
1. **无损**：所有 `target_unit` 按顺序拼接 == `si_translation`
2. **全覆盖**：每个 `source_unit_id` 在所有 eval_units 中恰好出现一次
3. **相邻有序**：同一 eval_unit 内的 source_unit_ids 必须相邻且保持源文顺序
4. 每个 eval_unit 必须有 `reason`

---

## 4. Phase 3：目标侧盲证据抽取（TargetEvidenceAgent）

### 4.1 调用

```python
TargetEvidenceAgent(primary_client).analyze(sample_id, eval_units)
# 输入: [{"eval_unit_id": "E1", "target_unit": "..."}, ...]
```

**信息隔离**：`eval_unit_id` 仅用于定位。Agent 完全看不到 `source_unit_ids`、源文本、源抽取结果、参考译文。不得猜测原文、判断译对译错。

### 4.2 任务

调用 prompt `target_evidence_agent`（自动前置 Shared Semantic Extraction Protocol），执行与源侧**完全相同协议**的语义抽取：

- **Target Anchor**（TA1/TA2...）：按译文实际文本抽取。错误翻译也如实抽取（如译错的术语仍按译文文本抽为 A-TERM）。
- **Target Event**（TE1/TE2...）：按译文实际命题抽取。问句保留言语行为（E-SPEECH），观点保留立场（E-JUDG）。
- **Target Relation**（TR1/TR2...）：同源侧规则，默认空。

**不输出 importance / verdict / score。**

### 4.3 evidence_span 归一化

LLM 可能在中文 evidence_span 中插入多余空格。`_normalize_target_evidence()` 自动修正：当 evidence_span 不在对应 target_unit 中逐字出现时，通过去除空格后的子串匹配，将 span 映射为原文中正确的逐字片段。

---

## 5. Phase 4：流利度评估（FluencyAgent）

### 5.1 调用

```python
FluencyAgent(primary_client).evaluate(sample_id, translation)
```

**信息隔离**：只看 `si_translation`。看不到源文。

### 5.2 任务

评估译文**作为目标语言文本**的通顺度、语法正确性和可理解性。找出所有流利度问题。

每个 fluency_issue：
- `issue_id`：F1、F2、F3... 连续编号
- `target_span`：问题所在的逐字片段
- `issue_type`：问题类型
- `severity`：`minor` / `moderate` / `major` / `critical`
- `reason`：说明

同时输出 `fluency_assessment`（整体文字评估）。

**去重约束**：同一 `target_span` 不能出现两次（code 层强制校验）。

---

## 6. Phase 5：SI 表达评估（SIExpressionAgent）

### 6.1 调用

```python
SIExpressionAgent(primary_client).evaluate(source_card, translation)
```

**信息隔离**：看 `source_text` + `si_translation`。看不到参考译文。

### 6.2 任务

评估同传特有的表达问题：信息压缩导致的完整性损失、同传策略带来的冗余或不当简并、句子结构因同步要求而破碎等问题。

字段结构与流利度完全相同：`si_expression_issues`（X1/X2...）+ `si_expression_assessment`。同样的 severity 四级 + 去重约束。

---

## 7. Phase 6：组装目标评估卡（Target Eval Card）

```python
target_card = {
    "sample_id": ..., "system_name": ..., "si_translation": ...,
    "eval_units": alignment.artifact["eval_units"],
    "target_anchors": target.artifact["target_anchors"],
    "target_events": target.artifact["target_events"],
    "target_relations": target.artifact["target_relations"],
    "fluency_issues": fluency.artifact["fluency_issues"],
    "fluency_assessment": fluency.artifact["fluency_assessment"],
    "si_expression_issues": expression.artifact["si_expression_issues"],
    "si_expression_assessment": expression.artifact["si_expression_assessment"],
}
```

### 7.1 缓存复用

如果提供了 `cached_target_card`（通过外部 target card cache 文件加载），且内容验证通过（翻译文本一致 + 结构校验全部通过），则跳过 Phase 2–5，直接复用缓存的 target_eval_card 进入 Phase 7。

---

## 8. Phase 7：首轮判定（PrimaryJudgeAgent）

### 8.1 调用

```python
JudgeAgent(primary_client, "primary_judge_agent").judge(source_card, target_card)
```

**输入**（Judge 看不到原始文本）：

- `source_card`：只含 `source_units`、`source_anchors`、`source_events`、`source_relations`（结构化源语义）
- `target_eval_card`：只含 `eval_units`、`target_anchors`、`target_events`、`target_relations`（结构化目标语义）

**注意**：Judge 看不到 fluency_issues 和 si_expression_issues — 这些是独立维度，直接进入确定性计分，不经过 Judge 判定。

### 8.2 任务

对**每个源侧项目**逐一判定译文是否传达、传达了多少。输出三类判定：

- `anchor_judgements`（AJ1, AJ2...）
- `event_judgements`（EJ1, EJ2...）
- `relation_judgements`（RJ1, RJ2...）

**判定必须覆盖所有源项目，且顺序与源项目一致**（code 层校验：`actual_source_ids == expected_source_ids`）。

每个 judgement 字段：

| 字段 | 说明 |
|---|---|
| `judgement_id` | AJ1/EJ1/RJ1... |
| `source_*_id` | 引用的源项目 ID |
| `source_evidence_spans` | 从源卡**原样复制**的 evidence（不得修改） |
| `eval_unit_ids` | 引用的目标 eval_unit ID（只允许源项目所在 eval_unit ± 1 范围） |
| `target_*_ids` | 匹配到的目标项目 ID |
| `target_evidence_spans` | 从目标项目获得的 evidence |
| `verdict` | 见下表 |
| `confidence` | 0.0–1.0 |
| `reason` | 判定理由 |

### 8.3 Verdict 体系

**Anchor / Event** 合法 verdict：`correct`、`partially_correct`、`incorrect`、`missing`、`uncertain`

**Relation** 合法 verdict：`correct`、`weakened`、`incorrect`、`missing`、`uncertain`

（Relation 用 `weakened` 表示关系被削弱但还存在，等价于 Anchor/Event 的 `partially_correct`。）

**目标证据引用规则**：
- `correct` / `partially_correct` / `weakened` / `incorrect` → 必须引用 `target_*_ids` 和 `target_evidence_spans`
- `missing` → 不能引用目标证据（因为找不到）
- `uncertain` → 可引用也可不引用

---

## 9. Phase 8：独立复核（ReviewerAgent）

### 9.1 调用

```python
JudgeAgent(review_client, "reviewer_agent").judge(source_card, target_card)
```

**输入与 PrimaryJudge 完全相同**。使用独立的 prompt（`reviewer_agent`）和独立的 LLM（可以配置为不同 provider/model）。

执行与 PrimaryJudge 相同的判定任务，输出相同的结构。

### 9.2 模型独立性

如果 `review_client.provider_name != primary_client.provider_name` 或 `review_client.model_name != primary_client.model_name`，则 `independent_model = true`。否则复核仍独立调用但属于同一模型两次判断。

---

## 10. Phase 9：分歧检测与裁决（AdjudicatorAgent）

### 10.1 分歧检测

```python
_build_disagreement_cases(primary, review)

# 对每个 judgement：
if primary.verdict != review.verdict:
    → 分歧，进入裁决
elif primary.confidence < 0.60 or review.confidence < 0.60:
    → 任一方不确信，进入裁决
else:
    → 一致且确信，不进入裁决
```

`MIN_FINAL_CONFIDENCE = 0.60`（定义在 `validation.py`）。

### 10.2 裁决

```python
AdjudicatorAgent(review_client).adjudicate(
    source_card, target_card, disagreement_cases
)
```

裁决者使用 **review_client**。输入包含 source_card、target_eval_card 和 disagreement_cases（含 primary 和 reviewer 的两个版本）。

裁决必须覆盖所有分歧项，且不多不少正好一次（code 层校验：`set(actual) == disagreement_ids`）。

---

## 11. Phase 10：判定合并（Merge Judgements）

```python
_merge_judgements(primary, review, adjudication)
```

对每个 judgement：

- **如果被裁决过**（judgement_id 出现在 adjudication 中）：
  - 使用裁决结果（verdict + confidence + reason 均来自裁决）
  - `resolution = "adjudicated"`

- **如果未被裁决**（primary 和 reviewer 一致且都 confidence ≥ 0.60）：
  - verdict 取 primary 的值
  - **confidence 取两者的最小值**：`min(primary.confidence, review.confidence)`
  - `resolution = "primary_reviewer_agreement"`

每个最终 judgement 额外保留审计字段：`review_verdict`、`review_confidence`、`resolution`。

---

## 12. Phase 11：确定性计分（calculate_scores）

`calculate_scores()` 位于 `validation.py:192`，**完全由 Python 确定性执行，LLM 不参与**。

### 12.1 常量定义

```python
DIMENSIONS = ("anchor_fidelity", "event_fidelity", "relation_fidelity", "fluency", "si_expression")

DIMENSION_WEIGHTS = {
    "anchor_fidelity": 30, "event_fidelity": 25, "relation_fidelity": 20,
    "fluency": 15, "si_expression": 10,
}

VERDICT_VALUES = {
    "correct": 1.0, "partially_correct": 0.5, "weakened": 0.5,
    "incorrect": 0.0, "missing": 0.0,
}

SEVERITY_DEDUCTIONS = {"minor": 2.0, "moderate": 6.0, "major": 15.0, "critical": 35.0}

MIN_FINAL_CONFIDENCE = 0.60
```

### 12.2 Fidelity 维度（Anchor / Event / Relation）

三个 fidelity 维度使用**完全相同的加权公式**。

**算法**（以 `anchor_fidelity` 为例）：

```python
source_by_id = {item["source_anchor_id"]: item for item in source_card["source_anchors"]}
rows = final_judgements["anchor_judgements"]

total_weight = sum(item["importance"] for item in source_by_id.values())
decided_weight = 0
earned = 0.0
uncertain_weight = 0
low_confidence = 0

for row in rows:
    verdict = row["verdict"]
    weight = source_by_id[row["source_anchor_id"]]["importance"]

    if row["confidence"] < 0.60:
        low_confidence += 1

    if verdict == "uncertain":
        uncertain_weight += weight
        continue  # ← 跳过，不参与 earned/decided

    decided_weight += weight
    earned += weight × VERDICT_VALUES[verdict]
```

**三种结果**：

| 条件 | dimension_score | coverage | decision_status | applicable |
|---|---|---|---|---|
| `total_weight == 0`（源文无此类项目） | 100.0 | 100% | `not_applicable` | false |
| `decided_weight == 0`（全部 uncertain） | **null** | 0% | `no_decisions` | true |
| `decided_weight > 0` | `round(100 × earned / decided_weight, 2)` | `round(100 × decided_weight / total_weight, 2)` | `complete` 或 `partial_decisions` | true |

**解读**：
- `uncertain` 不伪装成错误，而是从已决定分母中排除 → 拉低 coverage，不拉低分数
- 如果维度的所有非 uncertain 项目都是 `correct`，该维度得满分 100
- 如果维度无任何源项目（如整段文本没有 relation）→ `not_applicable`，分数 100 但权重在总分中被置零

### 12.3 Delivery 维度（Fluency / SI Expression）

**扣分制**，独立于 fidelity 判定：

```python
for dimension, issues in [("fluency", fluency_issues), ("si_expression", si_expression_issues)]:
    deductions = [SEVERITY_DEDUCTIONS[issue["severity"]] for issue in issues]
    score = round(max(0.0, 100.0 - sum(deductions)), 2)
```

起始分数 100，每个 issue 按 severity 扣分，最低为 0。

**去重保证**：同一 `target_span` 不能出现在多个 issue 中（由 `validate_delivery_artifact()` 在 Phase 4/5 已校验）。这防止 LLM 用不同 severity/issue_type 对同一处问题重复扣分。

### 12.4 总分（加权平均）

```python
active_dimensions = [
    dim for dim in DIMENSIONS
    if dim in {"fluency", "si_expression"}  # delivery 维度永远 active
    or diagnostics[dim]["applicable"]       # fidelity 维度 applicable 才 active
]

active_weight = sum(DIMENSION_WEIGHTS[dim] for dim in active_dimensions)

final_score = round(
    sum(scores[dim] × DIMENSION_WEIGHTS[dim] for dim in active_dimensions)
    / active_weight,
    2
)
```

**权重重归一化示例**：

如果 `relation_fidelity` 不适用（源文无 relation）：

| 维度 | 原始权重 | 有效权重 |
|---|---|---|
| anchor_fidelity | 30 | 30 / 80 = 37.5% |
| event_fidelity | 25 | 25 / 80 = 31.25% |
| relation_fidelity | 20 | 0%（not applicable） |
| fluency | 15 | 15 / 80 = 18.75% |
| si_expression | 10 | 10 / 80 = 12.5% |
| **总计** | **100** | **100%** |

`effective_dimension_weights` 字段记录重归一化后的实际权重。

### 12.5 分数状态（score_status）

```python
if any(diagnostics[dim]["decision_status"] == "no_decisions"
       for dim in fidelity_dimensions):
    score_status = "provisional_no_decisions"
    final_score = null  # ← 无法产出有意义的分数

elif any(diagnostics[dim]["uncertain_importance_weight"] > 0
         or diagnostics[dim]["low_confidence_count"] > 0
         for dim in fidelity_dimensions):
    score_status = "provisional_review_required"

else:
    score_status = "final"
```

**三种状态**：

| score_status | 含义 | final_score | 参与正式均分？ |
|---|---|---|---|
| `final` | 全部决定且确信 | 数值 | ✅ 是 |
| `provisional_review_required` | 有不确定或低置信度项目 | 数值（仅供参考） | ❌ 否（单独列出） |
| `provisional_no_decisions` | 全部 fidelity 项目为 uncertain | **null** | ❌ 否 |

**设计理由**：不把"无法判断"显示成 0 分，也不基于余下维度生成容易误读的部分总分。

### 12.6 完整数学公式

设源文有 $n$ 类 fidelity 项目（anchor/event/relation），每类有 $m_k$ 个源项目：

**维度分数**（fidelity）：

$$S_k = 100 \times \frac{\sum_{i=1}^{m_k} w_i \cdot v_i \cdot \mathbb{1}[v_i \neq \text{uncertain}]}{\sum_{i=1}^{m_k} w_i \cdot \mathbb{1}[v_i \neq \text{uncertain}]}$$

其中 $w_i \in \{1, 2, 3\}$ 为 importance，$v_i \in \{1.0, 0.5, 0.0\}$ 为 verdict 数值映射。

若全部分母为 0：$S_k = \text{null}$，维度标记为 `no_decisions`。
若分子为 0 但源文无项目：$S_k = 100$，标记为 `not_applicable`。

**维度分数**（delivery）：

$$S_k = \max\left(0, 100 - \sum_{j} d_j\right)$$

其中 $d_j \in \{2, 6, 15, 35\}$ 为每个 issue 的 severity deduction。

**最终分数**：

$$S_{\text{final}} = \frac{\sum_{k \in \mathcal{A}} S_k \cdot W_k}{\sum_{k \in \mathcal{A}} W_k}$$

其中 $\mathcal{A}$ 为 applicable 维度集合，$W_k$ 为原始权重。

若任一 applicable fidelity 维度为 `no_decisions`，$S_{\text{final}} = \text{null}$。

---

## 13. Phase 12：叙述性总结（SummaryAgent）

### 13.1 调用

```python
SummaryAgent(primary_client).summarize({
    "sample_id": ...,
    "final_judgements": {...},       # anchor/event/relation 最终判定
    "fluency_issues": [...],
    "si_expression_issues": [...],
    "dimension_scores": {...},
    "score_diagnostics": {...},      # 每维度详细诊断
    "final_score": ...,
    "score_status": "...",
})
```

### 13.2 任务

基于**既有结构化结果**撰写一段文字总结，包含：
- `overall_judgement`：总体评价
- `main_strengths`：主要传达正确的方面
- `main_errors`：主要错误或遗漏
- `uncertain_points`：不确定性点

**约束**：SummaryAgent **只能概括既有结果，不能修改任何 verdict 或分数**。如果 LLM 输出结构校验失败，使用内置中文 fallback（硬编码一条通用说明），不抛异常。

---

## 14. Runner 执行机制

每个 Agent 通过 `Runner.run()` 统一执行：

```
1. LLM 调用
   - temperature = 0（固定）
   - response_format = {"type": "json_object"}
   - payload 以 JSON 字符串嵌入 user message

2. _canonicalize()
   - 从响应中提取 JSON
   - 强制注入 sample_id / system_name（防止 LLM 丢失身份字段）

3. normalizer（如有）
   - 仅 TargetEvidenceAgent 有此步骤
   - _normalize_target_evidence() 修正 evidence_span 空格问题

4. 结构校验（validator）
   - 每个 Agent 有专用 validator
   - 返回 issue 列表

5. 如果校验失败 → 修复（最多 MAX_REPAIR_ATTEMPTS = 2 次）
   - 调用 schema_repair prompt
   - 输入：stage_name + 原始输入 + 校验问题 + 待修复 JSON
   - 重新校验
   - 每次修复后也重新应用 normalizer

6. 如果仍失败 + 有 fallback → 使用 fallback
   - 仅 SummaryAgent 有 fallback

7. 如果仍失败 → raise ValueError
```

**容错设计**：每个 stage 有最多 2 次修���机会。修复 prompt 只处理结构问题（缺失字段、ID 不连续、evidence 不匹配等），不改语义判断。

---

## 15. 输出产物

```
results/<run_name>/
├── source/
│   ├── source_00_input.jsonl        # 输入样本（复制）
│   └── source_cards.jsonl           # 冻结源证据卡
├── target/
│   ├── target_00_input.jsonl        # 输入系统输出（复制）
│   └── target_eval_cards.jsonl      # 目标评估卡
├── score/
│   ├── score_01_primary_judgements.jsonl
│   ├── score_02_review_judgements.jsonl
│   ├── score_03_adjudications.jsonl
│   └── score_06_final_results.jsonl
├── agent_trace.jsonl                # 所有 LLM 调用：{task, provider, model, request_id, usage}
├── failures.jsonl                   # 失败记录：{stage, sample_id, system_name, error}
├── metrics.json                     # 聚合统计
├── run_manifest.json                # 输入/输出/Prompt/实现/计分规则的 SHA-256
└── report.html                      # 独立 HTML 报告
```

### 15.1 run_manifest.json

包含：
- `protocol_version`、`implementation_version`
- `implementation_hash`：agents.py + validation.py + pipeline.py 的 SHA-256
- `samples_sha256`、`outputs_sha256`：输入文件的 SHA-256
- `prompt_hashes`：10 个 prompt 的 SHA-256 manifest
- `scoring_policy`：dimension_weights、verdict_values、severity_deductions（固化计分政策）
- `primary_provider`/`primary_model`/`review_provider`/`review_model`
- `source_card_cache_sha256`/`target_card_cache_sha256`（如有）

### 15.2 final_result.jsonl

每个（sample, system）一行，包含完整的评估数据：
- 所有 source/target anchor/event/relation
- 所有 judgement（含 primary/reviewer/adjudication 信息）
- fluency/si_expression issues
- 五个维度分数 + score_diagnostics
- final_score + score_status
- score_summary + review 元数据

---

## 16. Metrics 聚合

`compute_metrics()` 按系统分组统计：

```python
for system in systems:
    final_rows = [row for row in system_rows
                  if row["score_status"] == "final"
                  and isinstance(row["final_score"], (int, float))]

    system_metrics = {
        "samples": len(system_rows),
        "average_score": mean([r["final_score"] for r in final_rows]),       # 正式均分
        "provisional_average_score": mean([r["final_score"] for r in provisional_rows]),
        "final_results": len(final_rows),
        "provisional_results": count(score_status != "final"),
        "unscored_results": count(final_score is null),
        "dimension_scores": {
            dim: mean([
                r["dimension_scores"][dim]
                for r in final_rows
                if isinstance(r["dimension_scores"].get(dim), (int, float))
                and dimension_is_applicable(r, dim)
            ])
        },
    }
```

**关键**：
- 正式 `average_score` 和系统维度均分**只聚合 `score_status == "final"` 的结果**
- 内容维度均分额外排除该维度 `applicable == false` 的结果
- `provisional_average_score` 单独列出，仅供诊断参考，**不参与正式排名**
- `unscored_results`（final_score = null）不进入任何均分

---

## 附录 A：各 Agent 的信息隔离规则总结

| Agent | 看到什么 | 看不到什么 |
|---|---|---|
| SourceCardAgent | source_text | 任何译文、参考译文 |
| AlignmentAgent | source_units + si_translation | 参考译文、源侧语义分析 |
| TargetEvidenceAgent | eval_unit_id + target_unit | source_unit_ids、源文、参考译文 |
| FluencyAgent | si_translation | 源文、参考译文 |
| SIExpressionAgent | source_text + si_translation | 参考译文 |
| PrimaryJudgeAgent | source_card + target_eval_card（结构化） | 原始文本、参考译文 |
| ReviewerAgent | source_card + target_eval_card（结构化） | 原始文本、参考译文、首轮判定 |
| AdjudicatorAgent | source_card + target_eval_card + disagreement_cases | 原始文本、参考译文 |
| SummaryAgent | 最终判定 + 分数 + 诊断 | 原始文本、参考译文 |

**共同规则**：
- 所有 Agent 看到的 system_name 均为 `"anonymous_system"`（真实名称由 code 层写入输出）
- 参考译文**永远不传入任何 Agent**
- Judge 只看到结构化证据卡（source_anchors/events/relations + target 对等物），看不到原始 source_text 或 si_translation

## 附录 B：ID 体系总结

| 前缀 | 含义 | 侧 | 编号规则 |
|---|---|---|---|
| S | source_unit | 源 | S1, S2, S3... |
| SA | source_anchor | 源 | SA1, SA2, SA3... |
| SE | source_event | 源 | SE1, SE2, SE3... |
| SR | source_relation | 源 | SR1, SR2, SR3... |
| E | eval_unit | 目标 | E1, E2, E3... |
| TA | target_anchor | 目标 | TA1, TA2, TA3... |
| TE | target_event | 目标 | TE1, TE2, TE3... |
| TR | target_relation | 目标 | TR1, TR2, TR3... |
| F | fluency_issue | 目标 | F1, F2, F3... |
| X | si_expression_issue | 目标 | X1, X2, X3... |
| AJ | anchor_judgement | 判定 | AJ1, AJ2, AJ3... |
| EJ | event_judgement | 判定 | EJ1, EJ2, EJ3... |
| RJ | relation_judgement | 判定 | RJ1, RJ2, RJ3... |

所有 ID 从 1 开始连续编号，无重复。由 validator 强制校验。

## 附录 C：待校准参数

Importance 定义、verdict 数值映射、severity deduction 值和维度权重是 v0.5 的预注册工程规则。必须使用人工标注集检查以下指标后再发布新协议版本：

1. **相关性**：系统评分与人工评分的 Spearman/Pearson 相关系数
2. **排序一致性**：系统排名的 Kendall τ 与人工排名的一致性
3. **维度独立性**：各维度分数的实际区分度（是否出现高度共线）
4. **敏感性**：importance weight 和 severity deduction 对最终排名的稳定性
5. **跨模型稳定性**：相同 prompt 在不同 LLM 上的评分一致性
