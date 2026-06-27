# EviSI-Eval v0.2 Legacy 评测协议说明

> 本文档描述旧规则模式。新的 LLM Agent 评分协议见 `SCORING_SPEC_V1_ZH.md`；正式评测不再以本协议作为最终方案。

## 核心修正

v0.2 明确规定：**transcript 是翻译质量评估的必填输入**。

没有源语转录时，系统不能判断译文是否忠实。比如只看到：

```text
我去上班。
我去打球。
```

如果不知道原文是什么，就无法判断哪一句是正确翻译。最多只能判断目标语是否通顺，不能判断翻译质量。

## 两种支持模式

### 模式一：reference_assisted

输入：

```text
transcript + offline_translation + si_translation
```

含义：

- `transcript` 是源语转录。
- `offline_translation` 是离线参考译文，相当于目标侧 label。
- `si_translation` 是同传系统最终译文。

用途：

- 适合正式 benchmark。
- 离线译文帮助判断目标侧命题覆盖。
- 评分仍以 transcript 和 Evaluation Card 为核心，不是简单比较两个译文字符串。

### 模式二：source_only

输入：

```text
transcript + si_translation
```

含义：

- 没有离线译文。
- 系统只能依赖源语 transcript 和同传译文。

用途：

- 适合没有人工参考译文的快速评测。
- 对数字、实体、否定、方向、范围等结构化事实仍可评估。
- 对跨语言命题等价判断会更保守，需要 LLM 或人工复核。

## 为什么加入命题层

v0.1 只做事实槽位，因此适合处理：

- Apple -> Google
- 15% -> 50%
- not approved -> approved
- at least -> at most

但它处理不好没有实体数字的句子，例如：

```text
I go to work.
我去上班。
我去打球。
```

这些错误不是事实槽位错误，而是**核心命题错误**。所以 v0.2 加入最小命题层。

## 当前归因规则

错误归因顺序：

```text
事实层 > 命题层 > 关系层 > 同传表达层 > 目标语层
```

当前已启用：

```text
事实层 + 最小命题层
```

同一错误只扣一次：

- 如果事实层已经扣了实体、数字、否定、范围等错误，命题层不重复扣分。
- 如果没有事实错误，但整体意思错了，命题层扣分。

## 当前 v0.2 的边界

已经支持：

- transcript-first 数据协议
- reference_assisted 模式
- source_only 模式
- 事实层评分
- 最小命题层评分
- 重叠错误去重
- benchmark 风格输出目录
- `metrics.json`
- `bad_cases.jsonl`
- `not_pass.jsonl`
- `report.html`

尚未完成：

- 完整命题拆分
- 逻辑关系评分
- 同传表达适配评分
- 目标语可接受度评分
- LLM 语义等价复核

## 下一步

下一步应围绕 GaoYao 的内在方法继续推进：

1. 固化数据契约，而不是只写脚本。
2. 建立 task/evaluator registry。
3. 将构卡、推理、评分、报告解耦。
4. 为每个阶段设计 smoke / pilot / full preset。
5. 每个输出都保留 bad cases 和 not pass。
6. 对高风险或歧义样本使用 LLM/人工复核，而不是让 LLM 直接打总分。
