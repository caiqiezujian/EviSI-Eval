# EviSI-Eval v0.2 Legacy 运行手册

> 本文档保留用于旧规则模式兼容。新的 LLM Agent 可执行流程见 `SKILL.md`。

本文档说明当前 v0.2 版本 Agent 如何从输入数据一步步运行到最终报告。

## 1. 当前范围

当前 Agent 是 v0.2 版本。它要求必须提供源语 `transcript`，并评估两类内容：

- 关键事实准确性
- 最小命题覆盖度

暂时不评分：

- 逻辑关系保持度
- 同传表达适配性
- 目标语可接受度
- 真实延迟或流式输出时延

这个范围是刻意收窄的：先把 transcript、事实层和最小命题层做稳定，再扩展到完整命题、关系和表达层。

没有 `transcript` 时，系统不能判断翻译忠实度。比如只看到“我去上班”或“我去打球”，但不知道原文是什么，就无法判断哪一个是好翻译。

## 1.1 两种评测模式

v0.2 支持两种模式：

| 模式 | 输入 | 用途 |
|---|---|---|
| `reference_assisted` | transcript + offline_translation + si_translation | 有离线译文 label 时使用，适合更稳定地判断目标侧语义覆盖 |
| `source_only` | transcript + si_translation | 没有离线译文时使用，跨语言语义判断会更保守，必要时进入 review |

## 2. 输入文件

运行需要两个输入文件。

### 源文样本

路径：

```text
data/labeled_raw_samples.jsonl
```

每一行是一条源文样本：

```json
{
  "sample_id": "case_001",
  "transcript": "Apple reported a 15% increase in revenue in Q2.",
  "offline_translation": "苹果公司报告第二季度收入增长15%。",
  "domain": "finance"
}
```

字段含义：

- `sample_id`：样本唯一 ID。
- `transcript`：源语转录文本，必填。
- `offline_translation`：离线参考译文，只用于辅助构建 Evaluation Card，不是评分标准。
- `domain`：领域标签，可选。

### 系统输出

路径：

```text
data/labeled_system_outputs.jsonl
```

每一行是某个同传系统的一条最终译文：

```json
{
  "sample_id": "case_001",
  "system_name": "sys_b_entity_number_bad",
  "si_translation": "谷歌第二季度收入增长了50%。",
  "expected_label": "critical_fact_error",
  "expected_errors": ["entity_mismatch", "percentage_mismatch"],
  "label_notes": "Apple 被译成谷歌，15% 被译成 50%，应触发封顶。"
}
```

字段含义：

- `sample_id`：必须与源文样本对应。
- `system_name`：系统名称。
- `si_translation`：要评估的同传最终译文。
- `expected_label`：人工预期标签，用于调试和对照。
- `expected_errors`：人工预期错误列表。
- `label_notes`：人工说明。

## 3. 第一步：构建 Evaluation Card

命令：

```powershell
python -m evisi_eval build-card `
  --input data/labeled_raw_samples.jsonl `
  --output data/labeled_cards.jsonl
```

运行时会发生什么：

1. Agent 读取每条源文样本。
2. 规则抽取器识别关键事实槽位：
   - 百分比
   - 金额
   - 数字
   - 日期和时间
   - 实体
   - 否定/极性
   - 方向
   - 范围
   - 模态
3. Agent 生成 `Evaluation Card`。
4. 卡片写入 `data/labeled_cards.jsonl`。

示例卡片字段：

```json
{
  "sample_id": "case_001",
  "transcript": "Apple reported a 15% increase in revenue in Q2.",
  "facts": [
    {
      "fact_id": "f_entity_001",
      "type": "entity",
      "source_span": "Apple",
      "canonical_value": "apple",
      "importance": 3,
      "must_preserve": true,
      "acceptable_variants": ["Apple", "Apple Inc.", "苹果", "苹果公司"]
    }
  ],
  "allowed_omissions": [],
  "forbidden_losses": []
}
```

关键点：真实评测时，`Evaluation Card` 必须先由人工审查。卡片就是后续评分的合同。

## 4. 第二步：运行评分

命令：

```powershell
python -m evisi_eval run-eval `
  --cards data/labeled_cards.jsonl `
  --outputs data/labeled_system_outputs.jsonl `
  --output data/labeled_eval_results.jsonl
```

运行时会发生什么：

1. Agent 读取已经冻结的 Evaluation Cards。
2. 对每个系统输出，逐项核验卡片中的 facts。
3. 每个 fact 得到一个 verdict：
   - `correct`：正确或等价
   - `incorrect`：表达了，但值错了
   - `missing`：应保留但缺失
   - `ambiguous`：无法稳定确认
4. 所有非 `correct` 的 verdict 会变成 attributed error。
5. 系统累计扣分。
6. 应用封顶规则。
7. 最终结果写入 `data/labeled_eval_results.jsonl`。

## 5. 评分逻辑

总分从 100 分开始。

当前 v0.2 启用事实维度和最小命题维度：

```text
关键事实准确性 = 35 分
核心命题覆盖度 = 25 分
```

最终分数公式：

```text
final_score = min(100 - deductions, lowest_triggered_cap)
```

归因原则：

```text
同一错误只扣一次。
如果事实层错误已经解释了语义损失，命题层只保留诊断信息，不重复扣分。
如果没有事实错误，命题层才负责扣分。
```

示例：

```text
Apple -> Google
15% -> 50%

封顶前原始分：89
触发封顶：实体错、数字错、多个 critical facts
最终分：55
```

## 6. 封顶规则

封顶规则用于防止“译文很流畅但关键事实错了”的输出拿高分。

| 触发条件 | 含义 | 上限 |
|---|---|---:|
| `critical_entity_mismatch` | 关键主体或对象错位 | 60 |
| `critical_polarity_error` | 否定或极性丢失/反转 | 60 |
| `critical_direction_error` | 上升/下降、批准/否决等方向反转 | 60 |
| `critical_scope_error` | 至少/最多/仅/全部等范围失真 | 60 |
| `critical_number_time_value_error` | 关键数字、日期、金额、时间错误 | 70 |
| `multiple_critical_facts` | 两个及以上关键事实错误 | 55 |

## 7. 第三步：导出报告

命令：

```powershell
python -m evisi_eval export-report `
  --input data/labeled_eval_results.jsonl `
  --output reports/labeled_demo_report.html
```

输出文件：

```text
reports/labeled_demo_report.html
```

报告会显示：

- 样本 ID
- 系统名称
- 人工预期标签
- 最终分数
- 封顶原因
- 归因错误

HTML 文件可以直接用浏览器打开。

## 8. 当前 labeled demo 结果

当前 demo 有 3 条源文，每条源文有 3 个系统输出。

结果摘要：

```text
case_001 sys_a_good                    score=100
case_001 sys_b_entity_number_bad       score=55 cap=critical_entity_mismatch
case_001 sys_c_missing_number          score=70 cap=critical_number_time_value_error

case_002 sys_a_good                    score=100
case_002 sys_b_polarity_bad            score=60 cap=critical_polarity_error
case_002 sys_c_missing_age             score=97

case_003 sys_a_good                    score=100
case_003 sys_b_scope_number_bad        score=60 cap=critical_scope_error
case_003 sys_c_missing_scope           score=60 cap=critical_scope_error
```

这些结果说明当前系统的预期行为：

- 好译文得到 100 分
- 关键实体、数字、极性、范围错误会触发封顶
- 较小的缺失事实会扣分，但不一定触发封顶

## 9. 一键运行 demo

可以直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_demo.ps1
```

这个脚本会依次执行：

1. 默认 demo 构卡
2. 默认 demo 评分
3. 默认 demo 报告导出
4. labeled demo 构卡
5. labeled demo 评分
6. labeled demo 报告导出
7. mode demo：同时演示 reference_assisted 与 source_only

也可以直接运行 GaoYao 风格的总控入口：

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

其中包含：

- `metrics.json`
- `results.jsonl`
- `bad_cases.jsonl`
- `not_pass.jsonl`
- `report.html`

## 10. API Key 配置

当前 v0.1 是规则模式，不需要 API key 也能运行。

后续如果要加入 LLM 复核，使用：

```powershell
copy .\local_secrets.py.example .\local_secrets.py
```

然后编辑：

```text
local_secrets.py
```

填入：

```python
OPENAI_API_KEY = "your-key"
```

测试连通性：

```powershell
python -m evisi_eval check-api
```

不要把 API key 粘贴到聊天、源码或 README 中。

## 11. 模块位置

| 功能 | 文件 |
|---|---|
| CLI 命令 | `evisi_eval/cli.py` |
| Evaluation Card 构建 | `evisi_eval/card_builder.py` |
| 事实核验 | `evisi_eval/verifier.py` |
| 命题核验 | `evisi_eval/proposition_verifier.py` |
| 评分与封顶 | `evisi_eval/aggregator.py` |
| Benchmark 总控流程 | `evisi_eval/pipeline.py` / `run_eval.py` |
| 归一化规则 | `evisi_eval/normalization.py` |
| HTML/CSV 报告导出 | `evisi_eval/report.py` |
| 数据模型 | `evisi_eval/models.py` |
| API key 读取 | `evisi_eval/config.py` |
| API 连通性检查 | `evisi_eval/api_check.py` |
| Card Schema | `schemas/evaluation_card.schema.json` |
| Fact Verdict Schema | `schemas/fact_verdict.schema.json` |
| Final Score Schema | `schemas/final_score.schema.json` |
| 标注指南 | `annotation_guideline_v1.md` |

## 12. 如何添加新测试用例

1. 在 `data/labeled_raw_samples.jsonl` 添加源文。
2. 在 `data/labeled_system_outputs.jsonl` 为该源文添加 3 个系统输出。
3. 重新构建 cards。
4. 必要时人工审查并修改 cards。
5. 运行评分。
6. 导出报告。

建议每条源文配置：

- 一个正确/较好输出
- 一个关键事实错误输出
- 一个部分缺失或边界错误输出

## 13. 已知限制

- 规则抽取仍可能多抽或漏抽事实。
- 严肃评测必须人工审查 Evaluation Card。
- 当前版本只实现了最小命题层，还不是完整命题图。
- 跨语言 source-only 模式仍需要 LLM 或人工复核。
- 中文数字词支持还不完整。
- 命题层和关系层已经规划，但当前没有启用。

## 14. 建议下一步

1. 增加 30-50 条真实样本。
2. 人工审查 Evaluation Card 的 facts 和 aliases。
3. 只对歧义或高风险样本加入 LLM verifier。
4. 最小命题层稳定后，再启动完整命题拆分和关系评分。
