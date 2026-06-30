# EviSI-Eval v0.5 代码审查报告

审查日期：2026-06-29
审查范围：`evisi_eval/` 全部模块 + `prompts/` 全部 Prompt + `tests/` 全部测试

> 2026-06-30 修复状态：两个 P0 已解决。全 uncertain 维度现在输出 `null/no_decisions`，样本总分为 `null/provisional_no_decisions`；正式聚合只使用 `score_status=final`，临时均分单独报告且不参与排名，不适用内容维度也不进入维度均分。新增 3 个回归测试，当前共 22 个测试通过。

> 2026-06-30 稳健性补充：Relation 单元约束改为“存在、唯一、有序但可非连续”；HTTP 客户端增加 IncompleteRead 等瞬时故障重试，默认 timeout 提升至 900 秒；结构修复上限改为 2 次。

> 2026-06-30 真实 smoke 复跑：增加经重新验证的 Source/Target Card 跨 run 缓存、逐字 evidence 确定性归位，并修复未知 target item 导致的 KeyError。当前 29 项本地测试通过；DeepSeek v4 Flash 实际流程完成 1 个正式结果，`num_failures=0`。

## 一、总体评价

**v0.5 是一个工程上严肃、可审计的多 Agent 评测系统**，不再是"一个 Prompt 走完全流程"。整体架构对应了 2025 年主流的 **Supervisor + Workers + Reviewer + Adjudicator** 模式，融合了 LLM-as-a-Judge 与 Agent-as-a-Judge 的核心思想。19 个测试全部通过，代码风格统一，没有 TODO/FIXME 残留。

原始审查识别了 9 处问题；其中两个影响分数正确性的 P0 已于 2026-06-30 修复，其余问题仍按下文跟踪。

---

## 二、已经做对的事情（值得保留）

### 1. 信息隔离在代码层强制，不依赖 Prompt 自觉

- `agents.py:151-171` TargetEvidenceAgent 构造 payload 时**只取 `eval_unit_id + target_unit`**，没有 source 字段
- `tests/test_agents.py::test_target_evidence_agent_cannot_see_source` 验证 payload 序列化后 `Mark left.` 字符串、`source_` 字段名都不能出现
- `agents.py:213-228` Reviewer 的 payload 与 Primary 完全相同（结构上），但通过 `Runner.run` 调用不同 prompt，且 prompt 自身声明"看不到首轮"
- `tests/test_agents.py::test_reviewer_is_blind_to_primary_and_real_system_name` 验证 Reviewer payload 不含 `primary`/`judgement` 字样，且不含真实 `system_name`

### 2. 冻结源卡 + 一次构建多处复用

- `pipeline.py:94-110` 每个 sample_id 只调一次 `SourceCardAgent.build`
- 多个系统共享同一 `source_card_hash`（`test_pipeline.py::test_pipeline_builds_one_frozen_source_card_for_multiple_systems` 验证）
- `source_card_hash` 写入 `source_card.metadata`，同时复制到 `final_result`，跨阶段可追溯

### 3. 证据局部性（Evidence Locality）

- `validation.py:441-453` `_allowed_eval_ids` 限定判定只能在直接对齐的 eval unit 及其前后各一个相邻单元搜索
- `validation.py:411-425` 验证 target item 必须属于所引用的 eval unit，target evidence 必须从所引用的 target item 来
- `test_protocol_v05.py::test_judgement_rejects_non_local_target_evidence` 验证越界引用会被 catch

### 4. 独立复核 + 裁决机制

- `agents.py:286-287` PrimaryJudge、Reviewer、Adjudicator 是三个独立 LLM 调用
- `pipeline.py:60-66` Reviewer 默认同模型，`--review-provider` 可强制异模型
- `agents.py:435-458` `_build_disagreement_cases`：verdict 不同 **或** 任一 confidence < 0.60 都会触发裁决
- `agents.py:461-490` `_merge_judgements`：被裁决的 judgement 用 adjudication 替换，未裁决的取 min(primary.confidence, review.confidence)

### 5. 确定性计分

- `validation.py:191-277` `calculate_scores` 完全 Python 实现，verdict value、severity deduction、dimension weights 都是常量
- `test_protocol_v05.py::test_importance_weighting_and_uncertain_coverage_are_deterministic` 验证 score=100、coverage=75、status=provisional 的可重现性
- `test_protocol_v05.py::test_non_applicable_relation_weight_is_renormalized` 验证无 Relation 时其他维度权重重新归一化（不会白得 Relation 分）

### 6. Severity 去重

- `validation.py:145-147` 同 target_span 不能被同一表达维度多次扣分
- `test_protocol_v05.py::test_delivery_validation_rejects_duplicate_penalty_span` 验证

### 7. Manifest + 断点恢复

- `pipeline.py:254-277` `_manifest` 记录 protocol_version、implementation_version、implementation_hash、samples/outputs hash、prompt_hashes、provider/model、scoring policy
- `pipeline.py:280-283` `_assert_resume_compatible` 在 resume 时对比所有 manifest 字段，配置变化直接报错
- 这意味着换模型、改 prompt、改权重都不能继续上次 run

### 8. Prompt 合同级测试

- `tests/test_prompt_contracts.py` 验证所有 v0.5 prompt 都已注册、`source_evidence_agent` 包含"冻结"和"importance"、"target_evidence_agent"明确声明"看不到源文"、"primary_judge_agent`"包含"不计算分数"、"reviewer_agent`"包含"看不到首轮"、"summary_agent`"包含"不能改"
- 这层测试能在 prompt 改坏时立刻发现

---

## 三、需要关注的问题（按优先级）

### P0 — 影响分数正确性

以下两个问题均已修复，保留原始记录用于审计。

#### 问题 1：`decided_weight == 0` 时分数会变成 0.0（语义错误）

`validation.py:227`

```python
score = round(100 * earned / decided_weight, 2) if decided_weight else 0.0
```

**问题：** 当所有 source item 都是 `uncertain` 时，`decided_weight = 0`，分数会输出 `0.0`，被误读为"全部错误"。但 `score_status` 会被设为 `provisional_review_required`，可能造成 UI/报告上把 0.0 显示成失败。

**修复建议：**

```python
if total_weight == 0:
    score = 100.0
    coverage = 100.0
    applicable = False
elif decided_weight == 0:
    score = None  # 无可裁决项
    coverage = 0.0
    applicable = True
else:
    score = round(100 * earned / decided_weight, 2)
    coverage = round(100 * decided_weight / total_weight, 2)
    applicable = True
```

然后在 `final_score` 计算时跳过 None 值。

#### 问题 2：`compute_metrics` 把 provisional 和 final 一起平均

`pipeline.py:170-193`

**问题：** 系统级 `average_score` 包含 `provisional_review_required` 的样本，但 provisional 分数本身因为排除 uncertain 项而偏高，会拉高平均值，掩盖评测质量。

**现状：** `final_results` 和 `provisional_results` 已分开计数（line 179-180），但平均分计算仍混合。

**修复建议：** 同时输出 `average_score_final_only` 和 `average_score_including_provisional`，或要求用户显式选择。

---

### P1 — 工程质量

#### 问题 3：`_normalize_sample` / `_normalize_output` 在 `pipeline.py` 和 `dataset.py` 重复

- `pipeline.py:196-212`
- `dataset.py:56-72`

两处实现几乎相同但不完全一致（pipeline 版有 `unspecified` fallback，dataset 版没有；dataset 版有 `vid` alias 但 pipeline 版也有）。后续修改容易遗漏一处。

**修复建议：** 抽到 `dataset.py` 或新建 `evisi_eval/normalization.py`，两边 import。

#### 问题 4：`_implementation_hash` 只覆盖 3 个文件

`pipeline.py:286-289`

```python
payload = b"".join((root / name).read_bytes() for name in ("agents.py", "validation.py", "pipeline.py"))
```

`report.py`、`io_utils.py`、`llm_provider.py`、`config.py`、`cli.py` 改了不会让 hash 变化。理论上 prompt hash 已经覆盖了 prompt 层，但代码层行为变化（如 `calculate_scores` 公式改动）不会触发 resume 失败，可能导致新旧结果混入同一 run。

**修复建议：** 改为遍历 `evisi_eval/*.py` 全部模块，或显式列举全部相关文件。

#### 问题 5：缺一个 confidence<0.60 触发裁决的测试

`test_protocol_v05.py` 和 `test_agents.py` 都有 verdict 不同触发裁决的测试（`test_disagreement_triggers_adjudication`），但没有"primary 给 0.95、reviewer 给 0.55、verdict 相同"也触发裁决的测试。

**修复建议：** 加一个 `test_low_confidence_triggers_adjudication` 测试，明确这条路径。

---

### P2 — 设计与可读性

#### 问题 6：Source evidence prompt 体积过大

`prompts/source_evidence_agent.md` 18,129 字节，约 5K-6K token。DeepSeek 这种上下文大的模型没问题，但如果未来换成 GPT-3.5-turbo 或本地小模型可能截断。

**修复建议：** 把 Anchor 类型表、判定决策树拆分到附录，主文件保留操作指令。token 紧张时让 loader 按需拼接。

#### 问题 7：Summary fallback 是固定中文文本

`agents.py:264-271`

```python
fallback=lambda: {
    "score_summary": {
        "overall_judgement": "自动总结不可用，请直接查看结构化判定和计分诊断。",
        ...
    }
}
```

这个 fallback 文案写死，但报告 (`report.py`) 会展示它。如果 summary 失败，报告里会出现中文 fallback。**功能上没问题**，只是这个 fallback 本身不计入 `validation_log[summary_agent].fallback_used`，调试时难发现。

**修复建议：** 在 `_log_validation` 之外，记录 `fallback_used` 字段。

#### 问题 8：`MAX_REPAIR_ATTEMPTS = 1` 与文档描述不一致

`agents.py:26` 注释说"allow one structure-only repair"，但 `agent_architecture_review.md` 描述是"一次结构修复仍失败就写入 failure"，是一致的。**无问题**，只是命名值得统一。

#### 问题 9：`fluency_agent.md` 和 `si_expression_agent.md` 共用 `validate_delivery_artifact`

`validation.py:125-148` `validate_delivery_artifact` 通过参数化（`issue_key`、`assessment_key`、`prefix`）通用化。

**设计选择：** 这是一个不错的 DRY 实现，但调用者必须手动保证 prefix 对应 issue_key 与 schema 匹配。如果未来加新 delivery 维度（如 Prosody），要确保 prefix 不冲突。可以在函数里加 `_check_prefix_match` 防御性检查。

---

## 四、未在代码里但应纳入下一版本的考量

| 议题 | 现状 | 建议 |
|---|---|---|
| 人工金标 | 无 | 建 50-100 条多领域样本双人标注集 |
| 跨模型稳定性 | 单一模型默认，--review-provider 可异模型 | 报告里加同模型多次运行的方差 |
| 重要性 calibration | `importance=1/2/3` 是工程规则 | 用人工排序做相关性、敏感性分析 |
| 评测耗时 / 成本 | 未记录 | 在 metrics 里加 avg LLM 调用次数、token 数 |
| 评测可重复性 | manifest hash 已支持 | 把模型版本（具体 deepseek-chat-xxxxx）记入 manifest |
| 流式 SI 评测 | 不支持 | 明确协议边界，本版本只评最终文本（README 已经声明） |
| MQM 对齐 | severity 用 minor/moderate/major/critical 4 档，MQM 是 Minor/Major/Critical 3 档 | 文档化差异；或加 MQM 模式开关 |

---

## 五、值得点赞的细节

- `agents.py:511-516` `_canonicalize` 强制把 `sample_id` 和 `system_name` 覆盖回 payload 值，防止 LLM 编造样本 ID
- `agents.py:519-520` `_with_identity` 在写入 JSONL 前才注入真实 system_name，LLM 始终只见 `anonymous_system`
- `agents.py:552-555` `_artifact_hash` 用 `sort_keys + separators` 保证序列化结果稳定
- `pipeline.py:138-149` 即便 evaluation 失败，也把 source_card_hash 一并写入 failure，便于事后追溯
- `llm_provider.py:127-128` HTTP 重试只对 408/409/429/5xx 做指数退避，4xx 客户端错误不重试（避免烧 token）
- `validation.py:34-41` 把所有允许的 anchor/event/relation 类型做成模块常量，Prompt 和校验共用同一套定义

---

## 六、结论

**v0.5 是一个值得发表为工具的系统**，不是"还在搭"的状态。

核心优势：信息隔离、独立复核、确定性计分、证据局部性、Manifest 复现——这些是当前 LLM 评测工具的"高水位"特征。

建议优先处理两个 P0（问题 1、问题 2），其余可在后续小版本中迭代。

下一步如果要往 v1.0 推进，按 `docs/agent_architecture_review.md` 列出的 6 步走：
1. 人工标注 50-100 条样本的金标 source card
2. 双人标注 verdict
3. 仲裁
4. 计算抽取 F1、verdict 一致性、加权分与人工排序相关性
5. 做消融
6. 冻结 v1.0 协议
