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

## 3. 校验现有输入

```bash
python -m evisi_eval check-v06-input --samples data/user_samples.jsonl --outputs data/user_two_files_si_only_outputs.jsonl
```

该命令只做字段归一化和一致性检查，不调用模型。现有 `transcript/offline_translation` 会自动映射为 `source_text/reference_translation`，`system_asr` 被忽略。

## 4. 先跑一个样本

```bash
python -m evisi_eval run-v06 --samples data/user_samples.jsonl --outputs data/user_two_files_si_only_outputs.jsonl --provider deepseek --run-name v061_smoke --output-dir results --limit-samples 1 --limit-outputs 1
```

一个样本有多个系统时，所有系统都会跑；只跑一个输出可加 `--limit-outputs 1`，或加 `--system-name 系统名`。

## 5. 检查结果

先看 `results/v061_smoke/failures.jsonl`。为空时再看：

- `source/source_cards_v06.jsonl`：冻结 Source 义务。
- `reference/reference_projection_cards.jsonl`：Reference 辅助投影。
- `context/evaluation_context_cards.jsonl`：三阶段 hash 和 ID 映射。
- `target/si_projection_cards.jsonl`：同传逐项投影。
- `score/final_results_v06.jsonl`：逐项诊断、score status 和分数。
- `report.html`：浏览报告。

## 6. 失败处理

失败记录会说明 stage 和验证错误。先修 Prompt/契约或输入，再换一个新的 `run-name` 重跑。只有代码、Prompt、输入、模型和计分策略完全不变时才使用 `--resume`。

不要直接编辑中间 JSONL 后继续同一实验；这会破坏 manifest 对应的可复现条件。
