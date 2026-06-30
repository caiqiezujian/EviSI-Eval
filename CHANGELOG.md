# Changelog

## [0.5.0] - 2026-06-29

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
