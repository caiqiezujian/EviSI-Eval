# 评分协议

## 1. 维度权重

| 维度 | 权重 | 输入 |
|---|---:|---|
| 事实锚点准确性 | 30 | `anchor_alignments` |
| 事件语义保持 | 40 | `event_alignments` |
| 逻辑关系保持 | 10 | `relation_alignments` |
| 流利度与可理解性 | 12 | `fluency_issues` |
| 表达效率与简洁性 | 8 | `efficiency_issues` |

前三个内容维度共 80 分。关系维度在源文没有 required relation 时标记为不适用，总分按实际评估权重归一化，同时公开 `evaluated_weight`。

## 2. 内容维度公式

每个源项目的重要性为 1、2 或 3：

```text
item_budget = dimension_weight * item_importance / sum(dimension_item_importance)
item_deduction = item_budget * verdict_coefficient
dimension_score = dimension_weight - sum(accepted_item_deduction)
```

### 锚点系数

| verdict | 系数 |
|---|---:|
| exact / equivalent | 0 |
| incorrect / missing | 1 |
| ambiguous | 0，进入复核队列 |

### 事件系数

| verdict | 系数 |
|---|---:|
| covered / compressed_covered | 0 |
| partially_covered | 0.5 |
| contradicted / missing | 1 |
| ambiguous | 0，进入复核队列 |

### 关系系数

| verdict | 系数 |
|---|---:|
| preserved | 0 |
| weakened | 0.5 |
| reversed / missing | 1 |
| ambiguous | 0，进入复核队列 |

## 3. 目标语言扣分

流利度单项扣分为 minor 1、major 3、critical 6；表达效率单项扣分为 minor 0.75、major 2、critical 4。各维度扣分不会超过该维度满分。

简洁性不使用字符数或长度比。只评价可定位的无意义重复、重复改述、过量填充、无依据添加和可避免冗长。

## 4. 错误去重

- 事件的 `error_scope=anchor_only` 时，事件错误保留用于诊断，但不重复扣分。
- 关系的 `independent_error=false` 时，关系错误由关联事件错误解释，不重复扣分。
- 复核器给出 `duplicate_of` 时，后一个错误不重复扣分。
- 流利度不能因翻译含义错误扣分，表达效率不能因合理同传压缩扣分。

## 5. 复核门槛

候选错误只有在复核结果为 `valid` 且复核置信度不低于 0.70 时自动扣分。`invalid` 不扣分；`uncertain` 不扣分并进入人工复核队列。

## 6. 总分封顶

已确认的关键错误可触发总分封顶：

| 条件 | 上限 |
|---|---:|
| 关键事件被明确反译 | 55 |
| 关键关系被反转 | 60 |
| 关键事件完全缺失 | 65 |
| 关键锚点明确错误 | 65 |
| 存在关键不可理解片段 | 60 |

封顶只作用于已确认错误。报告同时保留 `score_before_caps`、`score_cap` 和触发证据。

## 7. 版本与校准

权重、系数、Prompt、模型和 schema 都进入运行清单。任何变更必须升级协议版本。获得稳定人工标注集后，应报告系统级排名相关性、样本级相关性、错误分类一致率和复核前后变化。
