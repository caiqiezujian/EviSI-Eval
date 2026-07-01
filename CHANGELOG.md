# Changelog

## [0.7.0] - 2026-07-01

> **协议版本**：`evisi_eval_v0.7` ｜ **实现版本**：`0.7.0`

### 核心重构

- **Source + Reference 联合抽取**：替换 v0.6 的 Source-先抽、Reference-后投影模式。Source 与 Reference 在 4 个对应阶段（Segment / Anchor / Event / Relation）一同抽取，由 Python 按位置 zip 为一张 Joint Card。**每个 sample 只做一次**，冻结后所有 SI 系统共享。
- **位置匹配取代 ID 交叉引用**：Source 数组第 i 条 ↔ Reference 第 i 条 ↔ SI 第 i 条，校验靠数组长度相等与逐位置 ID 匹配，**不再维护 ID 映射表**。消除 ID 漂移导致的复杂交叉校验。
- **SHA-256 冻结 Joint Card**：用 `artifact_hash()` 对所有非 metadata 字段计算 SHA-256，断点续跑时先校验 hash 再复用，避免不同 prompt/model/输入混入同一 run。
- **14 阶段流水线**（v0.6 的 16 阶段被重排、合并、聚焦）：
  - **Source 侧（4 calls/sample）**：Segment / Anchor / Event / Relation，全程不接触任何译文。
  - **Reference 侧（4 calls/sample）**：Align / Anchor / Event / Relation，仅辅助 SI 在目标语中定位内容。
  - **SI 侧（6 calls/system）**：Align / Anchor Match / Event Match / Relation Match / Fluency / SI Expression，匹配基于 Source 语义权威 + Reference 辅助。
- **Stage 级缓存 + Resume**：12 个 LLM 阶段（1-12）独立 JSON 缓存；Phase 13/14 直接调用。`run_manifest_v07.json` 记录 protocol_version、implementation_hash、prompt_hashes、provider/model、dimension_weights，任何一项变更即拒绝 resume。

### 协议层

- **Reference 改为辅助而非标准**：SI 与 Reference 不同不自动判错，SI 在目标语中给出与 Source 语义等价的表达即为 `equivalent`。
- **Relation 依赖阻断**：当 Relation 端点 Event 全部为 missing/contradiction 时，Relation 标记 `not_scored` 从分母排除，避免双倍惩罚。
- **`not_scored` validator**：声明 `not_scored` 的 Relation 必须其全部 `source_event_ids` 对应 Event 匹配为 missing/contradiction，否则报错（结构硬约束）。
- **5 维评分体系（确定性）**：anchor 35% / event 35% / relation 10% / fluency 12% / si_expression 8%。Match 值映射 `equivalent=1.0`、`partial=0.5`、`contradiction/missing=0.0`，`uncertain` / `not_scored` 从分母排除。`calculate_v07_scores()` 全部在 Python 端实现，**LLM 不参与计分**。
- **Source item 重要性加权**：Anchor / Event / Relation 的 `importance ∈ {1,2,3}` 作为评分权重，关键信息比背景信息对分数影响更大。
- **score_status 三态**：`final`（无 uncertain）/ `provisional_review_required`（存在 uncertain，需人工复审）/ `provisional_no_decisions`（所有 fidelity items 均为 uncertain → `final_score=null`）。
- **信息隔离矩阵**：14 个 Agent 各自的 Source / Reference / SI 可见性在 doc 第 12 章明确定义，代码层在 payload 组装时物理隔离。

### 实现层

- **新模块**：
  - `evisi_eval/v07_agents.py` — `V07JointCardBuilder`（Phase 1-8 + Joint Card 组装）、`V07SIMatcher`（Phase 9-14 + 调 `calculate_v07_scores`）。
  - `evisi_eval/v07_pipeline.py` — `run_v07_pipeline()` 编排、断点续跑、metrics 计算、离线 `check_v07_input_files()`。
  - `evisi_eval/v07_validation.py` — 14 个 validator + `calculate_v07_scores()` + 类型/权重/状态常量。
- **自包含 Prompt**：12 个 v07 prompt + 2 个 delivery agent prompt + 1 个共享 `schema_repair` prompt 全部独立完整，**无协议注入、无外部模板拼接**。
- **Flat JSON 输出**：所有 LLM artifact 均为扁平数组（`source_anchors[]`、`anchor_matches[]` …），无 `component_results` / `operators` 网格 / `hard_requirement` 结构。
- **Evidence 逐字校验**：所有 `source_evidence` / `reference_evidence` / `si_evidence` 必须为对应 segment 文本的逐字连续子串。修复 prompt 只修结构（ID 格式、数组长度、逐字性），不重做语义。
- **Runner 调度器**：每个 Phase 1 次 LLM 调用 → 结构验证 → 最多 2 次 `schema_repair` 修复 → 可选 fallback。失败记入 `failures.jsonl`，CLI 返回非零退出码。
- **HTTP client 韧性**：`HTTPJSONClient`（stdlib `urllib`）默认超时 900s，最多 3 次重试，仅对 transient 错误（408/409/429/5xx + 网络错误）重试。
- **CLI 扩展**：`check-input`（离线校验）、`check-provider`（连通性测试）、`run --resume`（hash 兼容断点续跑）、`--limit-samples / --limit-outputs / --provider / --output-dir / --run-name`。

### 测试

- `ScriptedLLMClient`：FIFO 响应队列，零 API key、零网络 I/O 的确定性 client。
- 7 个 pytest 全过：完整 14 阶段流水线、Joint Card 冻结与 hash、partial/contradiction/missing 非满分路径、输入非法时零 LLM 调用直接报错。
- 预制响应必须满足所有 validator 约束（无损拼接、连续 ID、evidence 逐字），并以 ID/数组长度贯穿阶段间依赖。

### 配套文档

- `docs/v0.7_protocol_design.md`（1557 行）— 完整协议设计：14 阶段详述、字段语义、硬约束表、信息隔离矩阵、Runner 调度、校验系统、确定性评分、stage 缓存、信息隔离、模块架构、CLI、输出结构、测试策略、约束清单、3 个附录（Prompt 清单、Type 枚举全集、关键设计决策记录）。
- `docs/assets/evisi_eval_v07_architecture_v2.png` — v0.7 流水线架构图（Joint Card Builder / SI Matching / Deterministic Scoring 三段式 + 五维权重可视化）。

### 移除 / 变更

- 移除 v0.6 的 source-conditioned projection 链路、Adjudicator 三模型复核、嵌套 `component_results` 结构、`hard_requirement` 列表。
- 旧 `docs/assets/evisi_eval_v07_architecture.png`（v1 草图）替换为 v2 学术风格版本。
- `docs/v0.7_design/`（设计草稿 00_architecture / 01_schema / 03_scoring）保留为设计过程记录，已被 `v0.7_protocol_design.md` 取代。

---

## [0.6.2] - 2026-07-01

- Source Event 改为按 Source Segment 独立抽取，解决整样本 Event 请求持续空响应的问题。
- Event 新增 `coverage_units`，强制解释每段原文属于 Event、允许省略或不可恢复残句，防止空数组静默漏抽。
- Source、Reference 和 SI Projection 增加逐子阶段缓存，恢复运行只重试未完成阶段。
- Projection Agent 按 Anchor/Event/Relation 发送最小必要 Source/Reference 视图，减少重复上下文。
- Agent trace 增加真实调用耗时；结构修复恢复为最多两次；畸形 JSON 自动重试一次。
- 默认最大输出从 32768 调整为 16384，并将运行参数纳入 manifest 兼容校验。
- 模型生成且未人工核验的 Source Card 只产生 provisional 分数，不再把覆盖不完整的结果标记为 final。
- CLI 在存在 pipeline failure 时返回非零退出码。

## [0.6.1] - 2026-06-30

- 新增零 LLM 调用的 Evaluation Context Card，显式绑定 Source/Reference hash 与逐项 ID 映射。
- SI Card 和最终结果增加 `reference_card_hash`、`evaluation_context_hash`，断点恢复校验完整输入溯源。
- Anchor Projection 禁止修改冻结 source component，强化目标值、逐字证据和 omission 约束。
- Event 的 arguments、五类 operators 和 target event structure 改为严格结构校验。
- 评分诊断增加逐 Source item 的权重、状态、贡献及 Anchor/Event 子状态，不引入未校准经验分值。
- 修复 Relation 全部被 Event 端点阻断时错误导致整份样本无最终分数的问题。
- 清除 Prompt 中来自测试数据的特征案例，改用独立合成案例，并新增 Prompt/Benchmark 隔离测试。
- 增加 `check-v06-input`，可离线确认现有 `transcript/offline_translation` 数据是否可直接运行。
- 删除失效的共享 Prompt 钩子、旧 PowerShell 运行脚本、临时调试文件和 6 月 29 日前的生成输出。

## [0.6.0] - 2026-06-30

- Source 拆分为 Segment、Anchor、Event、Relation 四个聚焦 Agent，并冻结为唯一事实义务卡。
- Reference 与 SI 改为 Source 条件化投影，不再自由建立与 Source 无关的目标语语义卡。
- Reference 只辅助解释目标语表达；SI 与 Reference 不同不自动判错。
- 硬约束只记录单个 exact target form、exact value/unit 或 required event semantics，不维护译法白名单/黑名单。
- Event 使用 predicate、arguments、operators 的结构化缩句，Anchor 值错误不重复扣 Event。
- Relation 在端点 Event 不可用时标记 `blocked_by_event/not_scored`，避免依赖错误重复扣分。
- 新增 v0.6 Prompt 模块、Schema、验证器、Pipeline、`run-v06` CLI 和端到端测试。

## [0.5.1] - 2026-06-30

- Source 与 Target 共用同一套 Anchor/Event/Relation 定义、类型边界、粒度和排除规则。
- Relation 改为默认不抽取；只有显式线索或置信度不低于 0.85 的强语义蕴含才允许输出。
- Relation 增加 `relation_basis`、`relation_cue` 和 `confidence`，并强制连接至少两个真实 Event。
- 增加仅执行 Source 抽取、对齐、Target 抽取的独立脚本和分阶段结果文件。
- 抽取断点恢复必须匹配 manifest，并重新验证所有缓存；旧协议卡不能作为新协议缓存继续运行。

## [0.5.0] - 2026-06-29

- 允许 Relation 引用非连续但有序的证据单元，继续拒绝无效、重复或乱序引用。
- 网络层增加 IncompleteRead/空响应/截断 JSON/连接中断重试，默认超时调整为 900 秒。
- 最大结构修复次数由 1 次调整为 2 次，降低单个 evidence span 错误导致整条样本失败的概率。
- 增加经过重新验证的 Source/Target Card 跨 run 缓存复用，避免网络失败后重复执行已完成阶段。
- 修复 judgement 引用未知 target item 时 validator 抛出 KeyError 的问题。
- 增加目标 evidence 空格差异到逐字原文的确定性归位，并记录 normalization notes。
- 修复全 uncertain 维度被错误显示为 0 分的问题；改为 `no_decisions` 和空最终分数。
- 修复系统正式均分混入 provisional 结果的问题；正式与临时聚合完全分离。
- 源证据卡改为每个样本一次构建并冻结，多个系统共享同一 source card。
- 拆分对齐、目标侧盲证据抽取、Fluency 和 SI Expression，消除目标抽取的源文污染。
- 增加独立首轮 Judge、盲 Reviewer 和按分歧/低置信度触发的 Adjudicator。
- LLM 不再生成分数；Python 按 importance、verdict、severity 和固定权重确定性计分。
- 增加 evidence locality、严格 ID 映射、coverage、provisional 状态、Prompt/实现哈希和断点兼容检查。
- 重写中文 README、架构、数据契约、评分协议、操作指南和 JSON Schema。

## [0.3.0] - 2026-06-29

- 按新的 16 阶段协议完整重构源文、译文和评分链路。
- 引入共享 `source_card`、系统独立 `target_eval_card` 和 `final_result`。
- 每个阶段独立保存 JSONL，中间证据可审计。
- 五维分数由 LLM 根据结构化结果生成，总分由代码固定加权。
- 增加数据标准化、逐样本拆分、smoke 数据、系统匿名和参考译文隔离。
- 删除旧联合语义分析、硬编码扣分、封顶和二次错误复核实现。
