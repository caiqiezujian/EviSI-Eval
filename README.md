# EviSI-Eval Agent

EviSI-Eval（Evidence-driven Simultaneous Interpretation Evaluation）是面向同声传译最终译文的证据驱动评测 Agent。

当前实现遵循 `evisi_eval_v0.3` 协议。它只评估最终译文，不评估真实延迟、partial 输出、字幕稳定性、音频、系统 ASR 或语音播报。

## 核心流程

源文侧对每个样本运行一次：

1. 源文无损句子切分。
2. 源文 Anchor 抽取。
3. 源文 Event 抽取。
4. 源文 Relation 抽取。

每个系统译文独立运行：

5. 译文对齐式无损切分。
6. 译文 Anchor 抽取。
7. 译文 Event 抽取。
8. 译文 Relation 抽取。
9. 完整译文 Fluency 评判。
10. 完整译文 SI Expression 评判。
11. Anchor 忠实度判断。
12. Event 忠实度判断。
13. Relation 忠实度判断。
14. 全文忠实度复核。
15. 五维 LLM 评分。
16. 程序加权并由 LLM 生成总结。

参考译文只保存在输入和报告中，默认不传入上述核心阶段。系统名称对模型匿名。

## 五维权重

| 维度 | 权重 |
|---|---:|
| Anchor Fidelity | 30% |
| Event Fidelity | 25% |
| Relation Fidelity | 20% |
| Fluency | 15% |
| SI Expression | 10% |

五个维度由 LLM 根据已有 judgement、issue 和 review 评分；代码只检查结构并按固定权重计算总分。

## 输入

源文 JSONL：

```json
{"sample_id":"sample_001","source_text":"source transcript","reference_translation":"optional reference","src_lang":"en","tgt_lang":"zh","domain":"tech"}
```

系统译文 JSONL：

```json
{"sample_id":"sample_001","system_name":"system_a","si_translation":"final SI translation"}
```

旧字段 `transcript` 和 `offline_translation` 可由 `prepare-data` 自动转换。`system_asr` 会被移除。

## 配置 DeepSeek

环境变量：

```powershell
$env:DEEPSEEK_API_KEY="your-key"
$env:DEEPSEEK_MODEL="deepseek-chat"
```

也可复制 `local_secrets.py.example` 为 `local_secrets.py` 并填写本地配置。不要提交密钥。

验证连接：

```powershell
python -m evisi_eval check-provider --provider deepseek
```

## 准备数据

```powershell
python -m evisi_eval prepare-data `
  --samples data/user_samples.jsonl `
  --outputs data/user_system_outputs.jsonl `
  --output-dir data/user_samples_v03
```

转换后包含完整数据、逐样本目录和一条低成本 smoke 数据。

## 运行

运行 smoke 数据：

```powershell
python -m evisi_eval run `
  --samples data/user_samples_v03/smoke/source_00_input.jsonl `
  --outputs data/user_samples_v03/smoke/target_00_input.jsonl `
  --provider deepseek `
  --run-name user_smoke_v03
```

运行完整数据：

```powershell
python -m evisi_eval run `
  --samples data/user_samples_v03/source_00_input.jsonl `
  --outputs data/user_samples_v03/target_00_input.jsonl `
  --provider deepseek `
  --run-name user_full_v03
```

可使用 `--sample-id`、`--system-name`、`--limit-samples`、`--limit-outputs` 控制运行范围，使用 `--resume` 复用已完成的 source card 和 final result。

## 输出

每次运行在 `results/<run-name>/` 下生成：

```text
source/source_00_input.jsonl
source/source_01_units.jsonl
source/source_02_anchors.jsonl
source/source_03_events.jsonl
source/source_04_relations.jsonl
source/source_cards.jsonl

target/target_00_input.jsonl
target/target_01_eval_units.jsonl
target/target_02_anchors.jsonl
target/target_03_events.jsonl
target/target_04_relations.jsonl
target/target_05_fluency.jsonl
target/target_06_si_expression.jsonl
target/target_eval_cards.jsonl

score/score_01_anchor_judgements.jsonl
score/score_02_event_judgements.jsonl
score/score_03_relation_judgements.jsonl
score/score_04_global_review.jsonl
score/score_05_dimension_scores.jsonl
score/score_06_final_results.jsonl

metrics.json
report.html
run_manifest.json
failures.jsonl
```

## 开发验证

```powershell
python -m pytest -q
```

详细协议见 [需求与实施方案](docs/requirements-v0.3.md)、[Prompt Set](docs/prompt-set-v0.3.md)、[架构](docs/architecture.md) 和 [数据契约](docs/data_contract.md)。
