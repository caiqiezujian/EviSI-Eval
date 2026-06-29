# EviSI-Eval LLM Agent 评分协议 v1.0

## 1. 研究对象与边界

本协议评价同传系统的**最终译文质量**。必填输入是源语 `transcript` 和被测系统的 `si_translation`；`offline_translation` 可选，只用于辅助目标语表达与术语判断，不能取代原文。

支持两种模式：

| 模式 | 输入 | 说明 |
|---|---|---|
| `reference_assisted` | transcript + offline_translation + si_translation | 正式 benchmark 推荐模式 |
| `source_only` | transcript + si_translation | 无参考译文时由双语模型直接核验 |

本协议不使用各系统自己的 ASR 转录进行评分。没有 partial hypotheses、音频时间戳和增量输出时，不评价真实延迟、修订率、闪烁率或稳定性。这些指标未来进入独立的 Streaming Track，不能从最终文本臆测。

## 2. 总体原则

1. **大模型负责理解，程序负责计分。** LLM 构卡、寻找证据、给局部 verdict；LLM 无权输出最终分数。
2. **先构卡，后看系统输出。** Evaluation Card Builder 看不到系统名称和系统译文，避免针对某个系统调整标准。
3. **逐项判定，不打感觉分。** 每个事实、命题、关系和目标语问题都有独立 ID、证据、置信度与复核状态。
4. **不确定就弃权。** `ambiguous` 和证据不合法的判定不自动扣分。
5. **同一错误只扣一次。** 事实值、命题主干、关系和目标语问题的职责边界固定。
6. **封顶必须复核。** 只有重要度 3、证据有效且复核确认的错误可以触发总分上限。
7. **Provider 与评分协议解耦。** DeepSeek、OpenAI、Gemini 或其他兼容接口必须返回同一结构，最终聚合结果不依赖供应商自定义分数。

## 3. 端到端工作流

```text
输入审计
  -> Evaluation Card Builder Agent
  -> Card Schema/Span/Reference Validator
  -> Fact Verification Agent
  -> Proposition Verification Agent
  -> Relation Verification Agent
  -> Target Comprehensibility Agent
  -> Error Review Agent
  -> Deterministic Aggregator
  -> JSONL / Metrics / Review Queue / HTML Report
```

### 3.1 输入审计

每个样本必须有稳定 `sample_id` 和非空 `transcript`。每条系统输出必须有对应 `sample_id`、`system_name` 和非空 `si_translation`。重复样本 ID、缺失卡片或模型调用失败进入 `failures.jsonl`，不能静默计为 0 分。

### 3.2 Evaluation Card Builder

构卡模型只接收：

- transcript
- offline_translation（可选）
- src_lang / tgt_lang / domain

输出对象：

- `facts[]`：硬事实槽位
- `propositions[]`：原子核心意义
- `relations[]`：命题之间有意义的逻辑关系
- `terminology[]`：术语及可接受译法
- `allowed_omissions[]`：填充语、废弃启动、低信息重复
- `forbidden_losses[]`：绝不能以同传压缩为理由省略的内容

所有 `source_span` 必须逐字存在于 transcript。关系引用的 proposition ID 必须存在。卡片生成后计算 SHA-256 `card_hash`，正式 benchmark 应人工审核后将 `card_status` 冻结。

若句子、实体、命题、关系 cue 或术语不是原文中的连续逐字跨度，本地验证器会将对应条目剔除，并触发一次 Card Repair Agent。Repair Agent 只接收原文、初始卡片和验证错误，仍看不到系统译文。修复结果必须再次通过同一确定性验证；仍有错误时卡片保持 `review_required=true`。

## 4. 四维结构与权重

| 维度 | 权重 | 核心问题 |
|---|---:|---|
| 关键事实保真度 | 40 | 真实世界指代、数值、边界和立场是否准确 |
| 核心命题覆盖度 | 35 | 听众是否收到完整的事件、行动、结论和建议 |
| 逻辑关系保持度 | 15 | 条件、因果、转折、比较、先后和归属是否保持 |
| 目标语可理解性 | 10 | 译文能否作为目标语被稳定理解 |

前三维合计 90 分，表示内容优先。前两维合计 75 分，避免流畅表达掩盖事实和主干意义错误。

若原文没有某类条目，例如不存在关键逻辑关系，该维度标记为 `not_applicable`。总分按实际适用权重归一化，并同时公开 `evaluated_weight`，不把未评价维度默认为满分。

## 5. 第一维：关键事实保真度（40）

### 5.1 事实类型

- number / percentage / money / unit
- date_time
- entity / term
- polarity
- direction
- scope
- modality

### 5.2 Verdict

| Verdict | 系数 | 定义 |
|---|---:|---|
| exact | 0 | 形式与值直接一致 |
| equivalent | 0 | 翻译、别名、缩写或改写后语义等价 |
| incorrect | 1 | 找到对应表达，但值或指代错误 |
| missing | 1 | 全文搜索后确认应保留内容缺失 |
| ambiguous | 0 | 证据不足，不自动扣分，进入复核 |

实体不能依靠大小写正则直接裁决。LLM 必须考虑翻译名、音译、简称、领域别名和上下文指代，例如 `COVID-19` 与“新冠肺炎”、`Mark` 与“马克”。

## 6. 第二维：核心命题覆盖度（35）

命题只描述“谁做了什么、发生了什么、结论/建议是什么”。已经进入 facts 的实体和数字通过 `linked_facts` 关联，命题核验时不重复处罚事实值。

| Verdict | 系数 | 定义 |
|---|---:|---|
| covered | 0 | 核心意义完整保留 |
| compressed_covered | 0 | 合理同传压缩后仍完整保留 |
| partially_covered | 0.5 | 只保留部分主干意义 |
| missing | 1 | 命题缺失 |
| contradicted | 1 | 译文表达了相反命题 |
| ambiguous | 0 | 无法稳定确认，进入复核 |

合理省略填充语、重复铺垫和废弃启动不扣分。数字、否定、条件、行动项和结论不属于合理压缩。

## 7. 第三维：逻辑关系保持度（15）

只抽取影响理解的关系：cause、condition、contrast、concession、comparison、purpose、temporal_order、exception、attribution、enumeration。普通 `and` 默认不构成关键关系。

| Verdict | 系数 |
|---|---:|
| preserved | 0 |
| weakened | 0.5 |
| missing | 1 |
| reversed | 1 |
| ambiguous | 0，进入复核 |

关系核验必须引用 `head_prop_id`、`dependent_prop_id`、原文 cue 和译文证据。否定或方向错误已经由事实维度承担时，关系层不得重复扣分。关系 verdict 必须包含 `independent_relation_error`；若为 false，该关系只保留诊断记录，不扣分。

## 8. 第四维：目标语可理解性（10）

本维只处理不重复改变原义、但妨碍目标语理解的问题：

- grammar_error
- sentence_fragment
- source_language_residue
- unnatural_collocation
- repetitive_surface
- unclear_reference
- register_mismatch
- unintelligible_segment

固定扣分为 minor=1、major=2.5、critical=5，维度累计最多扣 10 分。每个问题必须提供译文中的逐字 `target_span`；无法定位的风格印象不扣分。

## 9. 条目预算与确定性计分

前三维中每个条目的预算为：

```text
item_budget = dimension_weight * item_importance / sum(dimension_item_importance)
item_deduction = item_budget * verdict_coefficient
dimension_score = dimension_weight - sum(accepted_item_deduction)
```

importance 定义：

- 3：改变主体、结论、行动、风险、资格、法律/医疗/财务意义
- 2：重要支撑、主要限定或关键背景
- 1：低风险背景信息

importance 是构卡属性，不允许核验模型因某个系统表现好坏而修改。

## 10. 证据与复核协议

每个非正确 verdict 至少包含：item ID、source span、target span 或 null、confidence、reason。`target_span` 必须逐字存在于该系统译文，否则本地验证器将其改为 `ambiguous`。

处理规则：

- reviewer=`invalid`：不扣分；事实/命题/关系错误必须同时提供来自被测同传译文的 `counterevidence_span`
- reviewer=`valid` 且 confidence>=0.75：允许扣分
- reviewer=`uncertain`：importance=3 不扣分；非关键项只有主判 confidence>=0.90 时才可暂扣并保留复核标记
- 主判 confidence<0.75：不自动扣分
- ambiguous：永不自动扣分

复核 Agent 只回答“某一局部错误是否成立”，不能重新给整段译文打分。离线参考译文不能作为“系统已经翻出该内容”的反证。

## 11. 唯一归因

优先级固定为：

```text
fact > proposition > relation > target comprehensibility
```

但“事实错误优先”不等于关闭全部命题评分。命题 verdict 必须输出 `error_scope`。只有 `linked_fact_only` 避免重复处罚；`predicate` 和 `mixed` 中独立存在的命题损失仍继续评分。其他命题也始终独立核验。

## 12. 封顶规则

封顶是候选规则，不是单模型判决。只有复核有效的 critical 错误才能确认：

| 条件 | 总分上限 |
|---|---:|
| 关键事实明确错误 | 60 |
| 关键事实确认缺失 | 70 |
| 核心命题被反转 | 55 |
| 核心命题确认缺失 | 65 |
| 关键逻辑关系反转 | 65 |
| 大面积不可理解输出 | 55 |
| 两个及以上已确认 critical 错误 | 55 |

报告同时保留 `cap_candidates` 和已确认 `cap_reasons`，便于审计误封顶。

## 13. Provider 中立性

支持：

- DeepSeek：OpenAI-compatible Chat Completions
- OpenAI：OpenAI-compatible Chat Completions
- Gemini：原生 `generateContent`
- custom：任意 OpenAI-compatible endpoint

Provider 只影响局部语义分析。所有 Provider 必须遵循相同 JSON 字段、标签集、证据验证和聚合规则。报告记录 provider、model、request_id 和 token usage，但不记录 API Key。

## 14. 输出文件

每次运行生成：

- `cards/cards.jsonl`：完整 Evaluation Cards
- `evaluation_result/evisi_agent/results.jsonl`：逐系统逐条完整判定
- `evaluation_result/evisi_agent/partial_results.jsonl`：逐条 checkpoint，用于断点续跑
- `metrics.json`：系统均分、四维均分、错误和复核数量
- `bad_cases.jsonl`：已确认错误样本
- `review_queue.jsonl`：待人工或异构模型复核项
- `failures.jsonl`：调用、数据或 Schema 失败
- `report.html`：原文、参考译文、系统译文、四维得分和逐项证据
- `run_manifest.json`：输入哈希、模型、协议、权重与运行范围

## 15. 科学有效性要求

代码可运行不等于 benchmark 已有效。正式发布前还必须完成：

1. 至少 30-50 条人工审核 Evaluation Cards 的 pilot 集。
2. 实体、数字、否定、条件、合理压缩和幻觉增译 challenge set。
3. 同一译文重复评测的一致性检验。
4. 不同 Provider verdict 的一致率与分歧分析。
5. 与人工错误标注的 precision/recall/F1。
6. 权重与封顶规则的敏感性分析和消融实验。
7. 至少 200 条锁定测试集后再发布系统排名。

在这些验证完成前，报告必须标记为 pilot，不宣称最终模型优劣。
