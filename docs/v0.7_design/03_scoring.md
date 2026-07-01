# EviSI-Eval v0.7 — 评分规则

## 1. Match 值映射

| match | 分值 | 说明 |
|-------|------|------|
| `equivalent` | 1.0 | SI 完全覆盖了该义务 |
| `partial` | 0.5 | 覆盖核心但有关键缺失/弱化 |
| `contradiction` | 0.0 | SI 表达了冲突内容 |
| `missing` | 0.0 | SI 未覆盖该义务 |
| `uncertain` | 不进入分母 | LLM 无法稳定判断 |
| `not_scored` | 不进入分母 | 仅 Relation：端点 Event 不可用 |

## 2. 维度分数计算

```
dimension_score = (earned_weight / decided_weight) * 100

其中：
  earned_weight  = Σ(item.importance × match.value)  对所有 decided items
  decided_weight  = Σ(item.importance)                 对所有 decided items
  decided items   = match 不为 uncertain 且不为 not_scored 的 items
```

## 3. Relation 依赖阻塞

```
if relation 涉及的任一 source_event 的 SI match 为 missing/contradiction:
    → match = not_scored
    → 不进入 relation 维度分母（不在 relation 维度重复扣分，根因在 Event 维度已扣）

if 所有 relation 均为 not_scored:
    → relation 维度 blocked_by_dependency
    → 维度退出总分权重（不影响最终分数的计算）
```

## 4. 维度权重

沿用 v0.6，待校准：

| 维度 | 权重 |
|------|------|
| anchor_fidelity | 35 |
| event_fidelity | 35 |
| relation_fidelity | 10 |
| fluency | 12 |
| si_expression | 8 |
| **总计** | **100** |

## 5. 最终分数

```
final_score = Σ(dimension_score × weight) / Σ(applicable_dimension_weight)

where:
  applicable_dimension = 维度未被 blocked_by_dependency
  fluency / si_expression 始终 applicable
```

## 6. 分数状态

```
存在 uncertain items:
    → score_status = "provisional_review_required"
    → 需要人工复核

所有 fidelity items 均为 uncertain:
    → score_status = "provisional_no_decisions"
    → final_score = null

无 uncertain，无 blocked_by_dependency:
    → score_status = "final"
    → 分数可作为正式评测结果
```

> **实现说明**：`calculate_v07_scores` 当前根据 uncertain/blocked 状态推导
> `score_status`，不依赖 source items 的 `source_verification_status`。
> 后续若引入 `human_verified` 路径（v0.8+），需要在所有 source items
> 都通过人工复核时优先返回 `"final"`，当前默认按上述规则处理。

## 7. Item Decisions 诊断

每个内容维度（anchor/event/relation）输出 `item_decisions`：

```json
{
  "anchor_fidelity": {
    "total_items": 8,
    "decided_items": 7,
    "uncertain_items": 1,
    "blocked_items": 0,
    "decided_weight": 18,
    "earned_weight": 15,
    "item_decisions": [
      {
        "anchor_id": "S1_A1",
        "type": "term",
        "importance": 3,
        "source_text": "load balancing",
        "reference_text": "负载均衡",
        "si_text": "负载均衡",
        "match": "equivalent",
        "score_value": 1.0,
        "weighted_contribution": 3.0
      }
    ]
  }
}
```

这让报告能解释"哪一项贡献了多少分"。
