# Changelog

All notable changes to EviSI-Eval will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.1] - 2026-06-29

### Added
- **Sentence Aligner** (`prompts/sentence_aligner.md`): 句级对齐器，支持 1:1 / 1:N / N:1 / omitted / uncertain 五种对齐类型
- **Target Semantic Analyzer** (`prompts/target_semantic_analyzer.md`): 在冻结的 `target_units` 内抽取目标锚点、事件、关系
- **Semantic Aligner** (`prompts/semantic_aligner.md`): 基于句级对齐的项目级核验，输出 `error_scope` 与 `independent_error` 标志
- **Error Reviewer** (`prompts/error_reviewer.md`): 每个候选错误必须通过独立复核才能扣分
- **Schema Repair** (`prompts/schema_repair.md`): 失败关闭前的 LLM 修复流程
- 新增 `schemas/sentence_alignment.schema.json` 与 `schemas/target_analysis.schema.json`
- `.github/workflows/` CI 配置（计划）

### Changed
- 从 v0.3 的「Agent 多 Verifier」重构为「显式管线 + 两级对齐」
- Source Anchor Extractor 从纯字符串列表升级为结构化 anchor（`anchor_type` / `importance` / `required` / `confidence` / `attributes`）
- Source Event Extractor 增加 `attributes`（polarity / modality / direction / scope / tense_aspect）、`arguments`（agent / patient / theme 等角色）、`linked_anchor_ids`、`relations`、`allowed_omissions`
- 失败处理从模糊返回改为强制 raise（card builder / evaluator）
- 评分聚合完全确定性：`scoring.py` 纯 Python 计算所有维度分

### Removed
- 早期 `entity_extractor_v2.0_draft.md` / `v1.2_draft.md` / `v1.3_draft.md` 草稿
- 一次性 debug 脚本 `scripts/display_v203.py` / `display_v204.py` / `display_v205.py` / `inspect_v203.py` / `display_extraction.py`

### Schema
- `source_card.schema.json` 升级到 0.4.1（`event.required` 与 `event.importance` 字段正式化）
- `evaluation_result.schema.json` 升级到 0.4.1（增加 `sentence_alignment`、`target_analysis`、维度分与封顶理由）
- 新增 `sentence_alignment.schema.json` 与 `target_analysis.schema.json`

### Fixed
- 复核未通过的错误不再自动扣分（之前可能被错误计入维度分）

## [0.3.0] - 2026-05-15

### Added
- LLM Agent 评测协议 v0.3
- 多 agent verifier（card builder / aggregator / verifier）
- Pipeline 测试套件
- `run-agent` CLI 子命令

### Changed
- 从 v0.2 的 transcript-first 升级到 LLM agent 范式

## [0.2.0] - 2026-03-20

### Added
- 转录优先 v0.2 评测协议
- 本地示例输入/输出
- 评估管线基线

## [0.1.0] - 2026-02-10

### Added
- 初始 scaffold（BaseEval + registry + 数据契约）
- GaoYao 对齐文档