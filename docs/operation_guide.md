# 运行指南

## 1. 环境

要求 Python 3.10 或更高版本。

```powershell
cd D:\EviSI-Eval-Agent
python -m pip install -e .
```

测试依赖：

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
```

## 2. 配置模型

复制本地密钥模板：

```powershell
Copy-Item .\local_secrets.py.example .\local_secrets.py
```

只填写实际使用的 Provider。该文件已被 Git 忽略。也可以设置同名 Windows 环境变量。

```powershell
python -m evisi_eval check-provider --provider deepseek
```

## 3. 准备数据

标准输入分别是样本 JSONL 和系统输出 JSONL。若原始数据为一个对象中包含多个 `*_trans` 字段的宽表，可运行：

```powershell
python -m evisi_eval import-data `
  --input input1.txt input2.txt `
  --samples-output data/user_samples.jsonl `
  --outputs-output data/user_outputs.jsonl
```

导入器只读取 `*_trans` 作为待测同传译文；对应的 `*_asr` 可以保留在导入结果中，但当前评测不会使用。

## 4. 运行评测

```powershell
python -m evisi_eval run `
  --samples data/user_samples.jsonl `
  --outputs data/user_outputs.jsonl `
  --provider deepseek `
  --review-provider deepseek `
  --output-dir results `
  --run-name pilot_001
```

断点续跑：

```powershell
python -m evisi_eval run `
  --samples data/user_samples.jsonl `
  --outputs data/user_outputs.jsonl `
  --provider deepseek `
  --review-provider deepseek `
  --output-dir results `
  --run-name pilot_001 `
  --resume
```

如果输入、Prompt、模型、权重或版本发生变化，续跑会直接拒绝。此时应使用新的 `run-name`。

## 5. 检查结果

- `source_cards.jsonl`：检查源文锚点、事件和关系是否合理。
- `results.jsonl`：完整机器可读证据链。
- `metrics.json`：按系统汇总的分数和错误数量。
- `report.html`：适合人工浏览的逐样本报告。
- `review_queue`：当前没有足够证据自动扣分的项目。
- `failures.jsonl`：模型调用或结构校验失败，不能当作有效评测结果。

正式实验应先抽样审查 Source Card，再固定 Prompt、模型和配置运行所有系统。
