# EviSI-Eval Agent

> **Evidence-driven Simultaneous Interpretation Quality Evaluation System**

[![Protocol Version](https://img.shields.io/badge/Protocol-evisi_eval_v0.6-00d4ff?style=flat-square)](docs/v0.6_technical_design.md)
[![Implementation](https://img.shields.io/badge/Implementation-0.6.1-0066ff?style=flat-square)](pyproject.toml)
[![Python](https://img.shields.io/badge/Python-3.12+-4a90d9?style=flat-square&logo=python&logoColor=f7df1e)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/Tests-30%20passed-22c55e?style=flat-square&logo=pytest&logoColor=049d13)](tests/)
[![License](https://img.shields.io/badge/License-MIT-00d4ff?style=flat-square)](LICENSE)
[![DeepSeek](https://img.shields.io/badge/Model-DeepSeek%20V4%20Flash-0066ff?style=flat-square)](https://platform.deepseek.com/)
[![GitHub stars](https://img.shields.io/github/stars/caiqiezujian/EviSI-Eval?style=flat-square&logo=github&color=00d4ff)](https://github.com/caiqiezujian/EviSI-Eval/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/caiqiezujian/EviSI-Eval?style=flat-square&logo=github&color=4a90d9)](https://github.com/caiqiezujian/EviSI-Eval/network/members)

<picture>
  <source srcset="docs/assets/hero-banner.svg" type="image/svg+xml">
  <img src="docs/assets/hero-banner.svg" alt="EviSI-Eval Agent Architecture Banner" style="width:100%; border-radius: 12px; margin-bottom: 2rem;">
</picture>

---

## 评估范围

本项目评估**源语转录对应的最终同传文本**质量。不评估音频质量、ASR、首词延迟、平均滞后、增量字幕稳定性或语音播报质量。

## v0.6 核心思想

**Source 是唯一的事实权威。Reference 是辅助，不是参考答案。SI 的评分只看它是否忠实地把 Source 的内容传递出来。**

```
源文 ──▶ Source Card（Anchor / Event / Relation）
              │
              ├──▶ Reference Projection ──▶ Evaluation Context（哈希绑定）
              │                                      │
              └──▶ SI Projection ◀───────────────────┘
                         │
                         ├── Fluency
                         ├── SI Expression
                         └── 确定性评分
```

v0.6 不再让 target agent 独立抽取（语义空间不对齐），而是让 **reference 和 SI 都在 Source 的语义框架下做投影**，reference 用来建立每个 Source Item 的参考映射，SI 投影时能看到 reference 的结果作为辅助信息。

```bash
# 快速开始
python -m evisi_eval run-v06 \
  --samples data/user_samples.jsonl \
  --outputs data/user_system_outputs.jsonl \
  --provider deepseek \
  --output-dir results \
  --run-name my_run \
  --limit-samples 1 --limit-outputs 1

# 断点续跑
python -m evisi_eval run-v06 ... --resume
```

完整设计见 [v0.6 技术方案](docs/v0.6_technical_design.md)。

## 核心设计原则

| 原则 | 说明 |
|:---|:---|
| **Source 事实权威** | Source Card 一旦冻结，所有后续判断都以其为基准，不可篡改 |
| **条件化投影** | Reference 和 SI 都对照 Source 的 Anchor/Event/Relation 逐项投影，不独立抽取 |
| **Reference 辅助而非标准** | Reference 只辅助 SI 的投影，不作为"正确答案"评分 |
| **哈希溯源** | Source Card、Reference Card、Evaluation Context 均含 SHA-256 哈希，断点续跑时校验一致性 |
| **确定性计分** | 所有评分基于投影的 `mapping_status`（equivalent / partial / contradiction / missing）按公开规则计算，不依赖 LLM 的二次判断 |

> 在完成人工标注与一致性检验前，不应宣称评分已达绝对客观或成为成熟 benchmark。

## 流水线架构

```
源文
  │
  ├── Source Segment Agent ──────▶ source_segments
  ├── Source Anchor Agent ───────▶ source_anchors
  ├── Source Event Agent ─────────▶ source_events
  └── Source Relation Agent ──────▶ source_relations
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
          Reference Projection              Reference Projection
          (Anchor/Event/Relation)           (Anchor/Event/Relation)
                    │                               │
                    └───────────┬───────────────────┘
                                ▼
                     Evaluation Context
                     (哈希绑定 source + reference
                      + item_links 映射表)
                                │
          ┌─────────────────────┴─────────────────────┐
          ▼                                           ▼
  SI Alignment Agent                           SI Alignment Agent
  (lossless 切分)                              (lossless 切分)
          │                                           │
          ▼                                           ▼
  SI Anchor Projection                        SI Event Projection
  (看 source + reference)                     (看 source + reference)
          │                                           │
          └───────────────────┬───────────────────────┘
                              ▼
                    SI Relation Projection
                    (dependency_status 阻断机制)
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
         Fluency       SI Expression      确定性评分
```

## Agent 职责表

| Agent | 职责 | 信息边界 |
|:---|:---|:---|
| `V06SourceCardBuilder` | 源文分段、抽取 Anchor/Event/Relation、冻结卡片 | **仅源文** |
| `V06ProjectionBuilder` (reference) | Reference 译文投影到 Source，建立参考映射 | Source Card + Reference 译文 |
| `build_evaluation_context_v06` | 绑定 Source + Reference 哈希，生成 item_links | **确定性拼接**，无 LLM |
| `V06ProjectionBuilder` (si) | SI 译文在 Source 框架下投影，参考 Reference | Source Card + Reference Card + Evaluation Context + SI 译文 |
| `FluencyAgent` | 评估目标语通顺度 | **仅 SI 译文** |
| `SIExpressionAgent` | 评估同传特有表达问题 | Source + SI 译文 |

**注意：** v0.6 没有独立的 Judge Agent、Reviewer Agent、Adjudicator Agent——评分直接在 `calculate_v06_scores()` 中通过投影结果确定。

## 五维评分体系

| 维度 | 权重 | 测量对象 | 证据来源 |
|:---|---:|:---|:---|
| **Anchor Fidelity** | 35% | 实体、数字、单位、时间、术语、范围 | Anchor Projection `mapping_status` |
| **Event Fidelity** | 35% | 主体、动作/状态、对象、方向、否定、情态 | Event Projection `mapping_status` |
| **Relation Fidelity** | 10% | 因果、条件、转折、时序、比较等关系 | Relation Projection `mapping_status`（跳过 `blocked` 项） |
| **Fluency** | 12% | 目标语言本身的通顺度与可理解性 | Fluency Issue `severity` 扣除 |
| **SI Expression** | 8% | 同传表达的效率、冗余和组织负担 | SI Expression Issue `severity` 扣除 |

- Source 侧 items 按 `importance: 1 / 2 / 3` 加权
- `mapping_status` 映射：`equivalent=1.0`, `partial=0.5`, `contradiction / missing=0.0`
- Relation 端点事件未正确投影时，该 relation 标记 `not_scored`，不参与计算
- Hard Requirement（用户强制的精确匹配项）有独立追踪：违反时状态必须为 `contradiction`

## 快速开始

### 1. 安装

```bash
# 创建环境（推荐 Conda）
conda create -n evisi-eval python=3.12 pip -y
conda activate evisi-eval

# 安装依赖
pip install -e ".[dev,llm]"
```

### 2. 配置 DeepSeek

```powershell
# 设置用户级环境变量
[Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", "your-api-key", "User")
[Environment]::SetEnvironmentVariable("DEEPSEEK_MODEL", "deepseek-v4-flash", "User")

# 验证连接
python -m evisi_eval check-provider --provider deepseek
# ✅ 连接成功：provider=deepseek model=deepseek-v4-flash
```

> 也可复制 `local_secrets.py.example` 为 `local_secrets.py` 后填写（已被 `.gitignore` 忽略）。

### 3. 运行评测

```bash
# 先校验输入格式
python -m evisi_eval check-v06-input \
  --samples data/user_samples.jsonl \
  --outputs data/user_system_outputs.jsonl

# 运行 v0.6 流水线
python -m evisi_eval run-v06 \
  --samples data/user_samples.jsonl \
  --outputs data/user_system_outputs.jsonl \
  --provider deepseek \
  --output-dir results \
  --run-name my_run \
  --limit-samples 1 --limit-outputs 1
```

**断点续跑：** `--resume`（prompt、输入或模型哈希改变后需使用新的 `--run-name`）

## 输入格式

**样本文件**（每行一个源文）：

```json
{"sample_id":"sample_001","source_text":"...","reference_translation":"...","src_lang":"en","tgt_lang":"zh","domain":"general"}
```

**系统输出文件**（每个系统一行）：

```json
{"sample_id":"sample_001","system_name":"system_a","si_translation":"最终同传译文"}
```

- `transcript` / `offline_translation` 可分别作为 `source_text` / `reference_translation` 的兼容别名
- `system_asr` 被忽略
- 同一 `sample_id` 可对应多个系统输出

## 输出结构

```
results/<run-name>/
├── source/
│   ├── source_00_input.jsonl
│   └── source_cards_v06.jsonl          # 冻结源义务卡
├── reference/
│   └── reference_projection_cards.jsonl
├── context/
│   └── evaluation_context_cards.jsonl  # Source/Reference 哈希 + item_links
├── target/
│   ├── target_00_input.jsonl
│   └── si_projection_cards.jsonl       # 每个系统的源条件化投影
├── score/
│   └── final_results_v06.jsonl         # 逐项诊断与确定性分数
├── failures.jsonl                      # ⚠️ 先查这个
├── metrics_v06.json
└── run_manifest_v06.json               # 完整哈希链（可复现）
```

**检查顺序：** `failures.jsonl` → `score/final_results_v06.jsonl` → `metrics_v06.json`

## 本地测试

```bash
python -m pytest -q
# 30 passed — 使用 ScriptedLLMClient，无需 API Key
```

## 协议演进

```
v0.3  ────▶  v0.5  ────▶  v0.6.1 (当前)
早期抽取       双Agent复核     源权威 + 条件投影 + 哈希溯源
```

详见 [CHANGELOG.md](CHANGELOG.md)。

## 当前限制与下一步

| 状态 | 任务 |
|:---:|:---|
| ✅ 已完成 | Source/Reference/SI 条件化投影与可审计哈希链（v0.6.1） |
| 🔄 进行中 | 人工标注集构建（数字、实体、否定、情态、关系、同传压缩） |
| 📋 待做 | 双人标注与仲裁流程，项目级一致性（Krippendorff's α） |
| 📋 待做 | 不同 Judge 模型、Prompt 版本与多次运行的稳定性分析 |
| 📋 待做 | Benchmark 版本固化、模型快照与发布报告 |

## 文档

| 文档 | 说明 |
|:---|:---|
| [v0.6 技术方案](docs/v0.6_technical_design.md) | 字段定义、投影逻辑、评分算法完整规格 |
| [架构文档](docs/architecture.md) | Agent 职责边界与调用关系 |
| [数据契约](docs/data_contract.md) | 各 artifact 的 schema 与验证规则 |
| [评分协议](docs/scoring_protocol.md) | 五维评分算法与 provisional 处理 |
| [操作指南](docs/operation_guide.md) | 完整 CLI 手册与数据准备流程 |

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=caiqiezujian/EviSI-Eval&type=Date)](https://star-history.com/#caiqiezujian/EviSI-Eval&Date)

---

<p align="center">
  <img src="https://img.shields.io/badge/Made_With-Python_3.12+-4a90d9?style=for-the-badge&logo=python" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/AI_Provider-DeepSeek-0066ff?style=for-the-badge" alt="DeepSeek">
  <img src="https://img.shields.io/badge/Protocol-evisi__eval__v0.6-00d4ff?style=for-the-badge" alt="Protocol v0.6">
  <img src="https://img.shields.io/badge/License-MIT-00d4ff?style=for-the-badge" alt="MIT License">
</p>