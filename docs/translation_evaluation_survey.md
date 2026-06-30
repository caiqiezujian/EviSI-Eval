# 翻译质量评估与同传评测 Agent 调研报告

> 生成时间：2026-06-29
> 调研范围：MQM、GEMBA-MQM、LLM-as-Judge、Agent-as-Judge、同传评测

---

## 一、核心结论先行

| 维度 | 行业主流方案 | 你的方案 | 差距 |
|------|------------|---------|------|
| 错误分类体系 | **MQM 8 大类**（业界标准） | 3+2 类（自创） | ⚠️ 需要对齐 MQM |
| 评估范式 | **LLM-as-a-Judge** + **Agent-as-a-Judge** | 单一 MainAgent | ⚠️ 缺独立 Reviewer |
| 错误严重度 | 4 档（None/Minor/Major/Critical） | 2-3 档不统一 | ⚠️ 严重度体系混乱 |
| 分数计算 | 字错率 + 阈值判定 | 固定权重 + gap 分析 | ⚠️ 简单但不科学 |
| 评估粒度 | 错误级（error span） | 维度级（5 维分数） | ✅ 你的粒度更粗但更适合综合评分 |

---

## 二、MQM 框架（行业黄金标准）

### 2.1 MQM 简介

**MQM（Multidimensional Quality Metrics）** 是翻译质量评估领域最权威的框架，由德国人工智能研究中心（DFKI）开发，是 **WMT（国际机器翻译大会）** 官方评测标准。

### 2.2 MQM 8 大错误维度（最新版）

| 维度 | 中文 | 说明 |
|------|------|------|
| **Terminology** | 术语 | 术语翻译错误、不一致 |
| **Accuracy** | 准确性 | 误译、增译、漏译 |
| **Linguistic conventions** | 语言惯例 | 语法、拼写、标点（原 Fluency） |
| **Style** | 风格 | 语域、风格不一致 |
| **Locale conventions** | 区域惯例 | 数字、货币、时间格式 |
| **Audience appropriateness** | 受众适应性 | 文化适应性 |
| **Design and markup** | 格式与标记 | 排版、标记 |
| **Verity** | 真实性 | （旧版，现合并到受众适应性） |

### 2.3 MQM 错误类型详解

#### 准确性（最核心维度）
| 错误类型 | 说明 |
|---------|------|
| Mistranslation | 误译（意思错误） |
| Over-translation | 过译（翻译了不该译的） |
| Under-translation | 欠译（没翻译完整） |
| Addition | 增译（添加原文没有的内容） |
| Omission | 漏译（漏掉原文内容） |
| Untranslated | 未译 |
| Do not translate | 不应译 |

#### 语言惯例（原 Fluency）
| 错误类型 | 说明 |
|---------|------|
| Grammar | 语法错误 |
| Punctuation | 标点错误 |
| Spelling | 拼写错误 |
| Unintelligible | 不可理解 |
| Character encoding | 字符编码问题 |

### 2.4 MQM 严重度评分（4 档）

```python
MQM_SCORES = {
    "None": 0,        # 无错误
    "Minor": 1,       # 轻微错误
    "Major": 5,       # 主要错误
    "Critical": 10    # 严重错误
}
```

**MQM 评分公式：**

```
错误率 = Σ(错误数量 × 罚分值 × 权重) / 总字数
正确率 = (1 - 错误率) × 100
```

**与你的 Gap 分析法对比：**

| 维度 | MQM 公式 | 你的 Gap 分析 |
|------|---------|--------------|
| 基础 | 错误数 × 罚分 | correct + 0.5×partial |
| 严重度 | 4 档分值 | 单一权重 |
| 归一化 | 按字数 | 不归一化 |
| 输出 | 阈值判定（pass/fail） | 0-100 分 |

**问题：**
- 你的方法对"25万"和"公司名"错误一视同仁
- 没有按字数归一化
- 阈值判定更直接（pass/fail），不需要人为设权重

---

## 三、GEMBA-MQM（GPT-4 + MQM，最新实践）

### 3.1 论文信息

- **标题**：GEMBA-MQM: Detecting Translation Quality Error Spans with GPT-4
- **作者**：Tom Kocmi, Christian Federmann（微软）
- **发表**：WMT 2023
- **核心贡献**：第一个将 GPT-4 与 MQM 框架结合的自动评估方法

### 3.2 GEMBA-MQM 的核心方法

```
输入：源文 + 译文
        ↓
   GPT-4 评估（3-shot prompt）
        ↓
   输出：MQM 格式的错误标注
   [{ "span": "...",
      "category": "Accuracy/Mistranslation",
      "severity": "Minor/Major/Critical" }]
        ↓
   按 MQM 公式计算分数
```

### 3.3 GEMBA-MQM 的 prompt 设计（核心）

**关键创新：与语言无关的 prompt**

```
Given the following source and target text, identify translation errors.
Mark each error with:
- span: the exact substring in the target where the error occurs
- category: pick from MQM categories (Accuracy/Mistranslation, ...)
- severity: Minor / Major / Critical

Source: {src}
Target: {tgt}
```

### 3.4 GEMBA-MQM 的局限性

| 局限 | 说明 |
|------|------|
| 黑箱 GPT-4 | 依赖闭源模型，结果不可复现 |
| 错误识别不准 | 预测的错误与人类标注对齐度不高 |
| 不支持微调 | 无法针对特定领域优化 |
| 长度偏差 | 长文本可能漏检错误 |

### 3.5 后续改进工作：MQM-APE

**论文**：MQM-APE: Toward High-Quality Error Annotation Predictors with Automatic Post-Editing in LLM Translation Evaluators（arXiv:2409.14335）

**改进点**：
- 加入 APE（自动后编辑）作为验证信号
- 让 LLM 实际尝试修复错误，看修复后是否正确
- 提高错误标注的准确性

---

## 四、LLM-as-a-Judge 评估范式

### 4.1 定义

**LLM-as-a-Judge**：用 LLM 作为评估者来打分其他模型的输出。

**优势：**
- 解决 BLEU/ROUGE 等传统指标无法捕捉细粒度语义的问题
- 无需大规模标注数据
- 可解释性强（提供评分理由）

### 4.2 LLM-as-a-Judge 分类（综述 arXiv:2411.16594）

#### 按输入格式分类

| 类型 | 说明 | 适用场景 |
|------|------|---------|
| **Point-wise** | 逐点评估（单个样本） | 质量评分 |
| **Pair-wise** | 成对比较 | 偏好评估 |
| **List-wise** | 列表排名 | 多模型对比 |

#### 按输出格式分类

| 类型 | 说明 |
|------|------|
| **Score** | 打分（0-100） |
| **Rank** | 排序 |
| **Select** | 选择 |

#### 按评判内容分类

| 属性 | 说明 |
|------|------|
| Helpfulness | 有用性 |
| Harmlessness | 无害性 |
| Reliability | 可靠性 |
| Relevance | 相关性 |
| 综合质量 | 综合评估 |

### 4.3 LLM-as-a-Judge 的关键设计要素

根据 Piero Paialunga（Towards Data Science）的实战总结：

```python
# 1. 角色定义（明确身份和专业知识）
JUDGE_ROLE = """
You are a translation quality evaluator with expertise in
simultaneous interpretation. You assess translation quality
based on MQM framework.
"""

# 2. Few-shot 示例（覆盖不同场景）
FEW_SHOT_EXAMPLES = [
    # 正确、错误、部分正确都要覆盖
]

# 3. Chain-of-Thought 推理
COT_PROMPT = """
Think step by step:
1. Identify translation errors
2. Categorize each error (MQM categories)
3. Assess severity
4. Provide final score
"""

# 4. 结构化输出（用 Pydantic）
class JudgeResult(BaseModel):
    score: int  # 0-100
    verdict: str  # pass/fail
    confidence: float
    reasoning: str
    errors: list[ErrorSpan]
```

### 4.4 LLM-as-a-Judge 的已知缺陷

| 缺陷 | 说明 | 缓解方法 |
|------|------|---------|
| 长度偏差 | 倾向给长输出更高分 | 加入"简洁性"维度 |
| 位置偏差 | 倾向给先出现的更高分 | 打乱顺序多次评估取平均 |
| 自我偏好 | 倾向给自己生成的内容更高分 | 用不同模型做 judge |
| 评分方差 | 同一输入多次评估分数可能不同 | 每个样本评估 N 次取平均 |

---

## 五、Agent-as-a-Judge（2026 年新范式）

### 5.1 论文信息

- **标题**：Agent-as-a-Judge
- **作者**：Runyang You 等
- **来源**：arXiv:2601.05111（2026 年 1 月）
- **核心贡献**：用 Agent 替代单次 LLM 调用作为评判者

### 5.2 为什么需要 Agent-as-a-Judge？

LLM-as-a-Judge 的局限：
1. **固有偏见**（顺序、长度、自我偏好）
2. **单次推理浅薄**（single-pass reasoning）
3. **无法验证**（不能验证评估是否符合真实观察）

### 5.3 Agent-as-a-Judge 的核心能力

```
传统 LLM-as-a-Judge：单次 LLM 调用 → 评分

Agent-as-a-Judge：
Planning（规划评估步骤）
    ↓
Tool-augmented Verification（用工具验证）
    ↓
Multi-agent Collaboration（多 agent 协作）
    ↓
Persistent Memory（持久记忆）
    ↓
最终评分
```

### 5.4 对你的架构的启示

| Agent-as-a-Judge 能力 | 你的实现 | 差距 |
|---------------------|---------|------|
| Planning | ❌ 无 | 需加 Planner |
| Tool-augmented | ⚠️ 间接（有 repair） | 可直接用工具验证 |
| Multi-agent | ❌ 单 MainAgent | 需加 Reviewer |
| Persistent Memory | ❌ 无 | 需加 Mind-Map 类记忆 |

---

## 六、口译/同传质量评估

### 6.1 口译评估的特殊性

**同传 vs 笔译评估的关键差异：**

| 维度 | 笔译评估 | 同传评估 |
|------|---------|---------|
| 时间约束 | 无 | 极强（必须跟上发言） |
| 信息完整 | 期望 100% | 允许合理省略 |
| 流畅度 | 期望完美 | 允许口语化、停顿 |
| 内容压缩 | 视为损失 | 视为正常策略 |
| 增译 | 视为错误 | 可能是合理的连接 |

### 6.2 口译评估的主流模型

#### AIIC 质量评估标准（国际会议口译员协会）
- 信息准确传达
- 完整传达原意
- 术语专业
- 表达流畅
- 语速适当

#### Bühler 评估模型
- 信息对等
- 语言质量
- 发言规范
- 术语准确
- 同步质量
- 总印象

#### 张威（2010）评估框架
**结合内容评估 + 听众评估的双轨制：**
- 内容评估：忠实度、完整性
- 听众评估：可理解性、流畅性

### 6.3 同传评估的核心维度（业界共识）

```
┌─────────────────────────────────────────────┐
│         同传质量评估核心维度                  │
├─────────────────────────────────────────────┤
│ 1. 忠实度 (Fidelity)        [最重要]        │
│    - 信息准确性                              │
│    - 信息完整性                              │
│    - 逻辑关系保留                            │
├─────────────────────────────────────────────┤
│ 2. 表达 (Delivery)                          │
│    - 流利度                                  │
│    - 可理解性                                │
│    - 语速                                    │
├─────────────────────────────────────────────┤
│ 3. 语言 (Language)                          │
│    - 语法正确性                              │
│    - 术语专业性                              │
│    - 语域适当                                │
├─────────────────────────────────────────────┤
│ 4. 同步性 (Synchrony)                       │
│    - 延迟                                    │
│    - 跟读速度                                │
└─────────────────────────────────────────────┘
```

### 6.4 你的五维评分与业界对比

| 你的维度 | 业界对应 |
|---------|---------|
| anchor_fidelity | 忠实度（信息准确性） |
| event_fidelity | 忠实度（信息完整性） |
| relation_fidelity | 忠实度（逻辑关系） |
| fluency | 表达（流利度） |
| si_expression | 表达（同传策略） |

**你的评估体系在同传场景中是合理且完整的。**

---

## 七、你的架构与最佳实践的对比

### 7.1 整体评估流程对比

```
MQM/GEMBA-MQM 流程：
源文 + 译文 → LLM 一次性输出错误标注 → 按公式计算分数

你的流程：
源文 → SourceWorker 抽取 anchors/events/relations
                    ↓
译文 → TargetWorker 抽取 anchors/events/relations
                    ↓
          MainAgent 三步法定位 → judgement → 五维评分
                    ↓
                  修复+Review
```

### 7.2 优势

1. **更细粒度的评估**（每个 anchor 独立评判）
2. **证据链可追溯**（每个 verdict 有 evidence_span）
3. **结构化输出**（适合人机复核）
4. **信息隔离**（比一次性 prompt 更严格）

### 7.3 劣势

1. **依赖 LLM 多次调用**（成本高、可能不一致）
2. **缺乏 MQM 兼容性**（业界不直接认可）
3. **没有错误严重度量化**（无法按 MQM 公式计算）
4. **无独立 Reviewer**（评分合理性无保障）

---

## 八、具体改进建议

### 8.1 P0：评分体系对齐 MQM 标准

**建议：保留你的五维评分，但加入 MQM 错误标注**

```python
class MQMError(BaseModel):
    """MQM 格式的错误标注"""
    span: str  # 错误位置
    category: str  # MQM 类别
    severity: Literal["Minor", "Major", "Critical"]
    dimension: str  # 对应你的五维之一
    description: str
```

**好处：**
- 业界认可
- 可以计算字错率
- 适合人机复核

### 8.2 P0：明确严重度分值

```python
SEVERITY_SCORES = {
    "None": 0,
    "Minor": 1,
    "Major": 5,
    "Critical": 10
}
```

### 8.3 P1：添加 LLM-as-a-Judge 元素

**建议：让 MainAgent 在评分时提供：**
- Score (0-100)
- Verdict (pass/fail)
- Confidence (0-1)
- Reasoning (思考过程)

### 8.4 P1：添加 Reviewer Agent（Agent-as-a-Judge）

**基于 Agent-as-a-Judge 论文：**

```python
class ReviewerAgent:
    def review(self, main_result, source, target):
        # 1. Planning：制定审查计划
        plan = self._plan_review(main_result)

        # 2. Verification：用工具验证
        evidence = self._verify_with_tools(main_result, source, target)

        # 3. Multi-Agent Collaboration：调用多个 expert
        scores = self._multi_expert_review(evidence)

        # 4. 最终评分
        return self._aggregate_scores(scores)
```

### 8.5 P2：CoT 推理增强

**建议：在 MainAgent 的 prompt 中明确要求 CoT：**

```
请按以下步骤思考：
1. Step 1 - 证据定位
2. Step 2 - 证据检查
3. Step 3 - 得出结论
4. Step 4 - 严重度评估
5. Step 5 - 给出分数
```

---

## 九、参考资料

### 论文
1. **MQM (2014)**: Lommel et al., "Multidimensional Quality Metrics (MQM)"
2. **GEMBA-MQM (2023)**: Kocmi & Federmann, "GEMBA-MQM: Detecting Translation Quality Error Spans with GPT-4", WMT 2023
3. **MQM-APE (2024)**: Lu et al., "MQM-APE: Toward High-Quality Error Annotation Predictors with Automatic Post-Editing in LLM Translation Evaluators", arXiv:2409.14335
4. **Multi-Range Theory (2024)**: Lommel et al., "The Multi-Range Theory of Translation Quality Measurement", arXiv:2405.16969
5. **LLM-as-a-Judge 综述 (2024)**: arXiv:2411.16594
6. **Agent-as-a-Judge (2026)**: You et al., arXiv:2601.05111
7. **Knowledge-Prompted Estimator (2023)**: Yang et al., arXiv:2306.07486

### 框架/工具
- GEMBA GitHub: https://github.com/MicrosoftTranslator/GEMBA
- MQM Core Typology: http://themqm.info/typology/
- MQM Community: https://themqm.org/

### 口译评估文献
- 张威（2010）：科技口译质量评估
- 张威（2011）：会议口译质量评估调查
- 王斌华（2012）：口译评估模式建构
- AIIC 质量评估标准

---

## 十、总结

### 你的优势
1. **比 MQM 更细的粒度**：每个 anchor/event/relation 独立评判
2. **证据链可追溯**：每个 verdict 都有 evidence_span
3. **信息隔离严格**：比一次性 prompt 更可靠
4. **同传场景适配**：5 维评分符合同传评估业界共识

### 你最需要补的能力
1. **MQM 兼容性**：加入 MQM 错误标注
2. **严重度量化**：4 档严重度分值
3. **独立 Reviewer**：Agent-as-a-Judge 范式
4. **CoT 推理增强**：让评分过程更可解释

### 最优先改进
**加 MQM 错误标注层**——这是与业界对齐最快的路径，也让你的人工复核和系统对比成为可能。

---

*文档版本：v1.2*
*新增内容：MQM/GEMBA-MQM/LLM-as-Judge/Agent-as-Judge/同传评估调研*
