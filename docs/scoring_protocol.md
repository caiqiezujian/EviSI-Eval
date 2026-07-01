# EviSI-Eval v0.5 评分协议

## 内容维度

Anchor、Event、Relation 按源项目 `importance` 加权：

```text
correct = 1.0
partially_correct / weakened = 0.5
incorrect / missing = 0.0
```

```text
dimension_score = 100 × sum(importance × verdict_value) / decided_importance
coverage = 100 × decided_importance / total_importance
```

`uncertain` 不进入已决定分母，并计入 uncertain importance。这样不会把“不确定”伪装成“确定错误”，但任何 uncertain 或 confidence < 0.60 都会把结果标记为 `provisional_review_required`，同时报告 coverage。

如果某个适用内容维度的全部项目都是 `uncertain`，则该维度：

```text
dimension_score = null
decision_status = no_decisions
coverage = 0
```

此时样本 `final_score = null`，`score_status = provisional_no_decisions`。系统不会把“无法判断”显示成 0 分，也不会基于其余维度生成容易误读的部分总分。

源项目为空时，该维度为 not applicable，显示数值记 100，诊断中 `applicable=false`。计算样本总分时该维度权重置 0，其余适用维度按原权重比例重新归一化；`effective_dimension_weights` 记录实际权重。因此无 Relation 的样本不会白得 Relation 分。

## Importance

- `3`：改变身份、数字、结论、行动、风险、资格、法律/医疗/金融含义，或改变否定、方向、范围、情态。
- `2`：重要支持、约束、术语或时间地点条件。
- `1`：不改变核心结论、行动或风险的背景细节。

## 表达维度

Fluency 和 SI Expression 从 100 分开始，按每个非重复 issue 扣分：

```text
minor = 2
moderate = 6
major = 15
critical = 35
```

最低为 0。两个维度职责不同：Fluency 衡量目标语可理解性；SI Expression 衡量同传表达策略造成的额外负担。内容错误不得在这两个维度重复扣分。

## 总分

```text
Anchor 30% + Event 25% + Relation 20% + Fluency 15% + SI Expression 10%
```

分数由 Python 计算，任何 LLM Agent 都不能提交或修改维度分数。

## 系统级聚合

正式 `average_score` 和系统维度均分只聚合 `score_status=final` 的样本；内容维度均分还会排除该维度 `applicable=false` 的样本。待复核但仍有数值的结果单独进入 `provisional_average_score`，仅供诊断，不参与正式排名。`final_score=null` 的结果计入 `unscored_results`，不进入任何均分。

## 待校准参数

Importance 定义、verdict 数值、severity deduction 和维度权重是 v0.5 的预注册工程规则，不是已经由人工数据证明的最优参数。后续必须使用人工标注集检查相关性、排序一致性、敏感性与跨模型稳定性，再决定是否发布新协议版本。
