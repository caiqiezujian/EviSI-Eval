# 运行指南

1. 使用 `python -m evisi_eval check-provider --provider deepseek` 检查配置。
2. 使用 `prepare-data` 将旧字段转换为 v0.3 输入并生成逐样本目录。
3. 先运行 `data/<dataset>/smoke/`。
4. 检查 `failures.jsonl`、全部阶段 JSONL、`metrics.json` 和 `report.html`。
5. Prompt、输入、模型或权重未变化时可用 `--resume`。

评测失败时先查看失败发生在哪个阶段。不要手工修改最终分数；应修正对应 Prompt、输入或结构契约后使用新 run name 重跑。
