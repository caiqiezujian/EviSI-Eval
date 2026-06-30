# EviSI-Eval v0.5 架构

## 1. 设计原则

- **冻结基准**：一个源样本只调用一次 SourceEvidenceAgent，所有系统共享同一 `source_card_hash`。
- **职责分离**：对齐、目标抽取、表达评价、内容判定、复核、裁决、计分和总结分开执行。
- **信息隔离**：目标证据 Agent 物理拿不到源文；Reviewer 拿不到 Primary 的判定。
- **证据局部性**：内容判定只能使用直接对齐单元及前后各一个相邻单元，避免全篇碰巧匹配。
- **语义与数学分离**：LLM 负责语义结构和 verdict，Python 负责验证、覆盖率和分数计算。
- **失败显式化**：结构修复仍失败则记录 failure，不生成任意语义 fallback。
- **抽取协议对称**：SourceEvidence 与 TargetEvidence 运行时加载同一共享语义协议，保证 Anchor/Event/Relation 定义一致；两侧仍保持信息隔离。
- **关系稀疏性**：Relation 默认不存在，不把相邻、问答、同话题或文本顺序转换成语义关系。

## 2. 执行图

```text
每个 sample_id：
  SourceEvidenceAgent(source_text)
    -> validated frozen source card

每个 sample_id + system_name：
  AlignmentAgent(source_units, si_translation)
    -> eval_units
  TargetEvidenceAgent(eval_unit_id + target_unit only)
    -> target anchors/events/relations
  FluencyAgent(si_translation only)
    -> fluency issues
  SIExpressionAgent(source_text + si_translation)
    -> SI expression issues
  PrimaryJudgeAgent(source card + target card)
  ReviewerAgent(source card + target card, blind to primary)
    -> disagreement or confidence < 0.60 ?
       yes: AdjudicatorAgent
       no: agreement result
  deterministic calculate_scores()
  SummaryAgent(read-only result)
```

## 3. Agent 边界

| Agent | 可见输入 | 禁止职责 |
|---|---|---|
| SourceEvidence | 原文、语言、领域 | 看译文、打分、按系统重构源卡 |
| Alignment | source units、完整译文 | 抽取/评价/评分 |
| TargetEvidence | 目标单元 | 看源文、判断忠实度 |
| Fluency | 完整译文 | 判断误译漏译 |
| SIExpression | 原文、完整译文 | 重复处罚内容错误 |
| PrimaryJudge | 两侧结构化证据 | 重抽取、评分、总结 |
| Reviewer | 与 Primary 相同，但看不到 Primary 输出 | 迎合首轮结果 |
| Adjudicator | 争议 case 和两侧证据 | 处理未触发 case |
| Summary | 最终判定与代码分数 | 改 verdict 或分数 |

真实 `system_name` 不进入 LLM payload，统一使用 `anonymous_system`。参考译文只留档，不进入核心 Agent。

## 4. 验证和修复

每个 LLM 阶段执行一次生成；结构不合格时最多执行两次结构修复。验证覆盖：

- 必需数组和字段类型；
- ID 连续性与引用完整性；
- source/target 无损拼接；
- source unit 恰好覆盖一次；
- evidence span 逐字存在；
- judgement 与源项目严格一一对应；
- 目标证据属于引用的局部 eval units；
- verdict、confidence、severity 合法；
- 同一表达维度不重复处罚同一 target span。

Repair 只能修结构，不能重做语义。修复后仍失败，当前样本/系统写入 `failures.jsonl`。

## 5. 复现与恢复

`run_manifest.json` 记录输入哈希、Prompt 哈希、核心实现哈希、模型和计分策略。`--resume` 只有在这些字段全部一致时才允许继续，以免把不同实验条件混入同一 run。

纯抽取流程使用独立的 `extraction_manifest.json`，只执行 SourceEvidence、Alignment 和 TargetEvidence。恢复时除核对输入、模型、Prompt 与实现哈希外，还会重新验证已保存的 Source Card、Alignment 和 Target Semantic Card。缺少 manifest、缺少新 Relation 字段或逐字证据失效的旧产物都会被拒绝；应使用新的 `run-name` 重新生成。

## 6. 客观性边界

该架构把主观语义判断变为可定位、可复核的结构化判断，但 LLM verdict 仍是测量模型的输出。真正的 benchmark 有效性必须通过人工金标、标注者一致性、模型间稳定性和权重校准验证。
