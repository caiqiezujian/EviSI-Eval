# EviSI-Eval v0.5 架构审查

审查日期：2026-06-29。

## 结论

v0.5 已从“一个 LLM Prompt 完成抽取、判断、评分和总结”重构为可审计的多角色测量流程。它现在具备 Agent 系统需要的状态、角色边界、条件路由、独立复核、结构验证、失败恢复和确定性计算，不再只是顺序调用 Prompt。

但当前版本仍是**待校准评测系统**，不是已经证明客观有效的 benchmark。主要缺口不是再增加 Agent 数量，而是建设人工金标和验证测量有效性。

## 已解决的结构问题

### 1. 源基准漂移

源卡现在每个 `sample_id` 只生成一次，在任何系统译文进入判定前冻结。多个系统结果记录同一 `source_card_hash`，断点恢复复用同一卡片。

### 2. 目标抽取被源文诱导

对齐和目标证据抽取已经拆开。AlignmentAgent 可看 source units 与译文；TargetEvidenceAgent 只接收 `eval_unit_id + target_unit`，物理拿不到源文和源侧答案。

### 3. 同一模型自判、自审、自评分

PrimaryJudge 与 Reviewer 独立调用；Reviewer 看不到 Primary 输出。verdict 分歧、目标证据分歧或任一 confidence 低于 0.60 时进入 Adjudicator。LLM 不再生成任何分数。

### 4. 任意分数与免费维度

Python 按预注册 verdict value、importance、severity deduction 和维度权重计算。源文中不适用的内容维度权重置 0，其余维度重新归一化，不再因无 Relation 自动获得 20 分。

### 5. 证据只验证“全文出现”

判定验证现在要求：

- 源 evidence 与冻结源项目完全一致；
- eval unit 只能是直接对齐及相邻单元；
- 目标 item 必须属于所引用 eval unit；
- 目标 evidence 必须来自所引用 item；
- missing 不得引用目标证据；
- judgement ID 与源项目序号严格一一对应。

### 6. 语义 fallback 伪造结果

每阶段最多允许两次结构修复。修复仍失败就写入 failure，不再由 Python 生成 50 分或随意语义结果。Summary 的本地 fallback 只提示查看结构化结果，不改变分数。

## 当前 Agent 与职责

| Agent | 产出 | 关键隔离 |
|---|---|---|
| SourceEvidence | source units/anchors/events/relations/importance | 不看任何系统译文 |
| Alignment | eval units | 不抽取、不判断 |
| TargetEvidence | target anchors/events/relations | 不看源文 |
| Fluency | 目标语可理解性 issues | 不看源文 |
| SIExpression | 同传表达效率 issues | 不重复处罚内容错误 |
| PrimaryJudge | 首轮逐项 verdict | 不评分 |
| Reviewer | 独立逐项 verdict | 不看首轮结果 |
| Adjudicator | 争议项目最终 verdict | 只处理触发项目 |
| Summary | 只读摘要 | 不改 verdict/score |

## 目前仍未解决的问题

### 1. 源证据卡本身没有人工真值

SourceEvidenceAgent 的遗漏或过抽会直接改变评分分母。当前结构验证能检查 ID、逐字证据、类型和引用，但无法证明语义抽取完整。需要建立人工 source card 子集，报告 Anchor/Event/Relation 的 precision、recall 和 importance 一致性。

### 2. Judge 的语义等价判断仍依赖模型

双 Judge 和裁决降低单次随机判断风险，但同模型复核可能共享偏差。正式实验应至少比较：同模型多次运行、不同模型 Reviewer、人工 verdict 三者的一致性。

### 3. 参数尚未经验校准

`importance=1/2/3`、部分正确 0.5、severity 扣分 2/6/15/35、五维权重 30/25/20/15/10 都是 v0.5 工程规则。需要用人工总体排序或分数进行相关性、敏感性和消融分析。

### 4. 只评最终文本

当前不能测量真实同传延迟、修订轨迹、字幕稳定性、语音韵律或音频可懂度。未来如果加入流式日志，应作为独立 protocol，不应把无法观察的系统性能从最终文本中反推出来。

### 5. 成本与稳定性

每个源样本 1 次源构卡；每个系统输出至少 7 次调用，发生争议时增加裁决，结构失败时增加 repair。正式批量实验需要记录 token、延迟、失败率和每样本成本，并固定模型版本。

## 成为 benchmark 前的实施顺序

1. 人工标注 50-100 个多领域样本的 source units、Anchor/Event/Relation、importance。
2. 每个样本选择高、中、低质量同传结果，双人标注逐项 verdict 与表达 issues。
3. 对分歧执行人工仲裁，形成不可被评测模型看到的金标。
4. 计算抽取 F1、verdict 一致性、加权分数与人工排序相关性。
5. 做 Prompt、Judge 模型、Reviewer 模型、裁决开关、importance 和权重消融。
6. 根据结果冻结 v1.0 协议、数据版本、模型配置和报告模板。

## 发布标准建议

只有满足以下条件后才应称为 benchmark：

- 数据、标注指南和排除规则公开且版本化；
- 双人标注一致性和仲裁比例有报告；
- LLM Judge 对人工 verdict 的准确性有报告；
- 重复运行与跨模型方差有报告；
- 权重与扣分对系统排名的敏感性有报告；
- 所有系统在完全相同的冻结 source cards 和运行配置下评测。
