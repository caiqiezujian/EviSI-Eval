# EviSI-Eval Agent

面向**同传系统最终译文质量**的证据驱动评估框架。

当前仓库实现的是 v0.2 版本，核心目标不是让大模型直接“打感觉分”，而是把评估流程拆成可审查、可复现、可扩展的 benchmark pipeline。

## 当前能力

v0.2 已支持：

- 基于源语 `transcript` 构建 `Evaluation Card`
- 检查同传最终译文中的关键事实槽位
- 检查最小命题覆盖度，因此“我去上班 / 我去打球”这类没有实体和数字的句子也可以被评估
- 每个错误只归因到一个维度，避免重复扣分
- 固定扣分和总分封顶规则
- 导出 JSON / CSV / HTML 报告
- GaoYao 风格的 benchmark 输出目录：`metrics.json`、`bad_cases.jsonl`、`not_pass.jsonl`、`report.html`

## 关键前提

`transcript` 是必填输入。

没有源语转录时，系统无法判断翻译是否忠实。比如只看到：

```text
我去上班。
我去打球。
```

如果不知道原文是什么，就不能判断哪一句是正确翻译，最多只能判断目标语是否通顺。

## 两种评测模式

| 模式 | 输入 | 说明 |
|---|---|---|
| `reference_assisted` | `transcript + offline_translation + si_translation` | 有离线译文 label 时使用，更适合正式 benchmark |
| `source_only` | `transcript + si_translation` | 没有离线译文时使用，跨语言语义判断会更保守 |

其中：

- `transcript`：源语转录文本，必填
- `offline_translation`：离线参考译文，相当于目标侧 label，可选
- `si_translation`：同传系统最终译文

## 快速开始

进入项目目录：

```powershell
cd D:\EviSI-Eval-Agent
```

运行传统三步流程：

```powershell
python -m evisi_eval build-card --input data/raw_samples.jsonl --output data/cards.jsonl
python -m evisi_eval run-eval --cards data/cards.jsonl --outputs data/system_outputs.jsonl --output data/eval_results.jsonl
python -m evisi_eval export-report --input data/eval_results.jsonl --output reports/demo_report.html
```

运行 benchmark 风格总控流程：

```powershell
python run_eval.py `
  --samples data/mode_demo_raw_samples.jsonl `
  --outputs data/mode_demo_system_outputs.jsonl `
  --run-name mode_demo
```

输出目录：

```text
results/mode_demo/evaluation_result/evisi_eval/
```

包含：

- `metrics.json`
- `results.jsonl`
- `bad_cases.jsonl`
- `not_pass.jsonl`
- `report.html`

## 一键 Demo

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_demo.ps1
```

该脚本会依次运行：

1. 默认 demo 构卡
2. 默认 demo 评分
3. 默认 demo 报告导出
4. labeled demo 构卡
5. labeled demo 评分
6. labeled demo 报告导出
7. mode demo，即同时演示 `reference_assisted` 与 `source_only`

## 数据格式

源文样本：

```json
{"sample_id":"s1","transcript":"Apple reported a 15% increase in revenue in Q2.","offline_translation":"苹果第二季度收入增长15%。","domain":"finance"}
```

系统输出：

```json
{"sample_id":"s1","system_name":"sys_a","si_translation":"谷歌第二季度收入增长了50%。"}
```

带人工预期标签的系统输出：

```json
{"sample_id":"s1","system_name":"sys_b","si_translation":"谷歌第二季度收入增长了50%。","expected_label":"critical_fact_error","expected_errors":["entity_mismatch","percentage_mismatch"]}
```

## 推荐 v0.2 流程

1. 把 `transcript` 作为必填 ground truth 输入。
2. 如果有 `offline_translation`，启用 `reference_assisted` 模式。
3. 如果没有离线译文，启用 `source_only` 模式。
4. 人工审查生成的 `Evaluation Card`，尤其是 `facts[]`、`propositions[]` 和 `acceptable_variants`。
5. 运行 `run_eval.py` 生成标准化结果目录。
6. 查看 `metrics.json`、`bad_cases.jsonl`、`not_pass.jsonl` 和 `report.html`。

## 归因原则

系统遵守“同一错误只扣一次”原则。

如果事实层错误已经解释了语义损失，例如：

- 实体错
- 数字错
- 否定丢失
- 方向反转
- 范围错误

那么命题层只保留诊断信息，不重复扣分。

如果没有事实层错误，但整体意思错了，例如：

```text
原文：I go to work.
译文：我去打球。
```

则由命题层扣分。

## 文档入口

- 中文运行手册：[AGENT_RUNBOOK_ZH.md](AGENT_RUNBOOK_ZH.md)
- English runbook：[AGENT_RUNBOOK_EN.md](AGENT_RUNBOOK_EN.md)
- 评测协议说明：[EVALUATION_PROTOCOL_ZH.md](EVALUATION_PROTOCOL_ZH.md)

## API Key 配置

默认规则模式不需要 API key。

后续如果接入 LLM 复核，请不要把 key 写死进源码。使用本地私密文件：

```powershell
copy .\local_secrets.py.example .\local_secrets.py
```

然后编辑 `local_secrets.py`：

```python
OPENAI_API_KEY = "your-key"
```

`local_secrets.py` 已加入 `.gitignore`，不会被提交。

测试 API 连通性：

```powershell
python -m evisi_eval check-api
```

## 项目结构

```text
EviSI-Eval-Agent/
├── data/                         # 示例输入数据
├── evisi_eval/                   # 核心评估代码
│   ├── aggregator.py             # 扣分、封顶、归因聚合
│   ├── card_builder.py           # Evaluation Card 构建
│   ├── pipeline.py               # benchmark 总控流程
│   ├── proposition_verifier.py   # 最小命题层核验
│   ├── verifier.py               # 事实层核验
│   └── ...
├── prompts/                      # 后续 LLM 复核 prompt 模板
├── schemas/                      # JSON Schema
├── scripts/                      # Demo 脚本
├── tests/                        # smoke tests
├── run_eval.py                   # GaoYao 风格总入口
└── README.md
```

## 当前限制

- 当前命题层是最小实现，还不是完整命题图。
- 尚未实现逻辑关系保持度评分。
- 尚未实现同传表达适配性评分。
- 尚未实现目标语可接受度评分。
- 跨语言 `source_only` 模式仍需要 LLM 或人工复核。
- 中文数字词和复杂口语表达支持仍有限。

## 下一步

建议继续按 benchmark 标准化方向推进：

1. 增加真实同传样本。
2. 固化 `Evaluation Card` 人工审卡流程。
3. 加入 LLM verifier，但只用于歧义和高风险项。
4. 扩展完整命题拆分。
5. 扩展逻辑关系层。
6. 最后再加入同传表达适配和目标语可接受度。

