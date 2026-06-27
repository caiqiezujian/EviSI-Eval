# EviSI-Eval LLM Agent Skill

用于使用 DeepSeek、OpenAI、Gemini 或 OpenAI-compatible 模型，对同传最终译文执行证据驱动四维评价。

## 使用前输入

必须准备：

- `samples.jsonl`：`sample_id + transcript`，可选 `offline_translation/src_lang/tgt_lang/domain`
- `outputs.jsonl`：`sample_id + system_name + si_translation`
- 至少一个已配置 Provider

`system_asr` 可以存在于原始文件，但 Agent v1 不读取、不发送、不评分该字段。

## Step 1 - 配置 Provider

```powershell
copy local_secrets.py.example local_secrets.py
```

在被 Git 忽略的 `local_secrets.py` 中填写所用 Provider。DeepSeek 最小配置：

```python
EVISI_PRIMARY_PROVIDER = "deepseek"
EVISI_REVIEW_PROVIDER = "deepseek"
DEEPSEEK_API_KEY = "填写本地密钥"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
```

Pass gate：`local_secrets.py` 未被 Git 跟踪，且不在终端或日志打印密钥。

## Step 2 - 检查 Provider

```powershell
python -m evisi_eval check-provider --provider deepseek
```

Pass gate：输出 `Provider check passed`。失败时停止，不运行正式评测。

## Step 3 - 导入宽表数据（如需要）

```powershell
python -m evisi_eval import-wide `
  --input "C:\path\1.txt" "C:\path\2.txt" `
  --samples-output data/user_samples.jsonl `
  --outputs-output data/user_outputs.jsonl
```

Pass gate：样本数、系统数符合预期；每个 `sample_id` 唯一；每个输出都有对应样本。

## Step 4 - Pilot 运行

```powershell
python run_agent.py `
  --samples data/user_samples.jsonl `
  --outputs data/user_outputs.jsonl `
  --provider deepseek `
  --review-provider deepseek `
  --run-name pilot_deepseek
```

该命令依次执行：构卡、事实核验、命题核验、关系核验、目标语检查、错误复核、确定性聚合和报告导出。

Pass gate：

- `results/pilot_deepseek/cards/cards.jsonl` 存在
- `results/pilot_deepseek/run_manifest.json` 存在
- `metrics.json` 中 `failure_count=0`
- 每条结果包含四维结构、证据和 `agent_trace`

## Step 5 - 审核结果

依次检查：

1. `failures.jsonl`：必须为空。
2. `review_queue.jsonl`：确认待复核错误，不能把它们当成已确认错误。
3. `cards.jsonl`：检查 importance=3、实体别名、命题拆分、逻辑关系。
4. `report.html`：逐条核对 source span、target span、verdict 和 deduction。
5. `bad_cases.jsonl`：抽查所有封顶样本。

## Step 6 - 复用已构建卡片

卡片确认后，使用同一个 `run-name` 和 `--skip-card-build`，避免不同系统使用不同评分标准：

```powershell
python run_agent.py `
  --samples data/user_samples.jsonl `
  --outputs data/user_outputs.jsonl `
  --provider deepseek `
  --review-provider deepseek `
  --run-name pilot_deepseek `
  --skip-card-build `
  --resume
```

Pass gate：`run_manifest.json` 中输入哈希、模型和 card hash 可追溯。

运行期间每完成一条结果都会追加到 `partial_results.jsonl`。中断后使用 `--resume` 跳过已经完成的 `(sample_id, system_name)`。

## 失败处理

| 失败 | 处理 |
|---|---|
| Provider 401/403 | 检查本地 Key 和供应商权限，不打印 Key |
| Provider 429 | 降低并发或等待配额恢复 |
| JSON/Schema 错误 | 进入 failures；不得用自由文本猜测结果 |
| target_span 不在译文 | 自动改为 ambiguous，进入复核 |
| card source_span 不在原文 | 标记 card review_required |
| cap candidate 未复核 | 不应用封顶 |
| failure_count > 0 | 该次运行不作为完整 benchmark |

## 正式 Benchmark 门槛

正式排名前必须具备人工审核卡片、锁定测试集、Provider 一致性实验、人工错误标注对齐和权重敏感性分析。未达到时只能称为 pilot。
