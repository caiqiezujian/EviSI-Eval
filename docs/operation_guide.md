# EviSI-Eval v0.5 操作指南

## 1. 本地安装

安装 Python 3.12 64-bit（最低支持 Python 3.10），安装时启用 `Add Python to PATH` 和 Python Launcher。

推荐使用 Conda：

```bash
cd D:\EviSI-Eval-Agent
conda create -n evisi-eval python=3.12 pip -y
conda activate evisi-eval
python -m pip install -r requirements.txt
python -m pytest -q
```

或者：

```bash
conda env create -f environment.yml
conda activate evisi-eval
python -m pytest -q
```

不使用 Conda 时才采用下面的 venv 方式。

```powershell
cd D:\EviSI-Eval-Agent
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -q
```

## 2. 配置和检查 DeepSeek

确保新终端中存在 `DEEPSEEK_API_KEY` 和 `DEEPSEEK_MODEL`：

```powershell
python -m evisi_eval check-provider --provider deepseek
```

## 3. 转换宽表数据

```powershell
python -m evisi_eval import-data `
  --input data\user_samples.jsonl `
  --samples-output data\prepared\samples.jsonl `
  --outputs-output data\prepared\outputs.jsonl
```

如果文件已经符合 README 中的两份长表 JSONL 契约，可以跳过此步。

## 4. 先跑一个样本

直接运行准备好的脚本：

```powershell
.\scripts\run_smoke_deepseek.ps1
```

或运行等价命令：

```powershell
python -m evisi_eval run `
  --samples data\user_samples_v05\smoke\source_00_input.jsonl `
  --outputs data\user_samples_v05\smoke\target_00_input.jsonl `
  --provider deepseek `
  --run-name smoke_v05 `
  --output-dir results
```

一个样本有多个系统时，所有系统都会跑；只跑一个输出可加 `--limit-outputs 1`，或加 `--system-name 系统名`。

## 5. 检查结果

先看 `results/smoke_v05/failures.jsonl`。为空时再看：

- `source/source_cards.jsonl`：冻结源证据和 importance。
- `target/target_eval_cards.jsonl`：对齐、目标盲抽取和表达问题。
- `score/score_01_primary_judgements.jsonl`：首轮判断。
- `score/score_02_review_judgements.jsonl`：独立复核。
- `score/score_03_adjudications.jsonl`：仅争议/低置信度项目。
- `score/score_06_final_results.jsonl`：最终 evidence、coverage、score status 和分数。
- `report.html`：浏览报告。

## 6. 失败处理

失败记录会说明 stage 和验证错误。先修 Prompt/契约或输入，再换一个新的 `run-name` 重跑。只有代码、Prompt、输入、模型和计分策略完全不变时才使用 `--resume`。

不要直接编辑中间 JSONL 后继续同一实验；这会破坏 manifest 对应的可复现条件。
