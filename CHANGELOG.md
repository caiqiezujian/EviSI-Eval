# Changelog

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
