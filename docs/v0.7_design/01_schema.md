# EviSI-Eval v0.7 — 数据结构

## 1. Source Segment + Anchor 输出（Step 1）

```json
{
  "sample_id": "en2zh-01-tech_001",
  "source_segments": [
    {
      "seg_id": "S1",
      "source_text": "Round-robin um um load balancing scheme, so I'm not sure...",
      "anchors": [
        {
          "anchor_id": "S1_A1",
          "type": "term",
          "text": "Round-robin load balancing scheme",
          "evidence": "Round-robin um um load balancing scheme",
          "importance": 3
        }
      ]
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `source_segments[].seg_id` | S1, S2, S3... 连续编号 |
| `source_segments[].source_text` | 逐字原文，所有 segment 拼接 = source_text |
| `anchors[].anchor_id` | 段内编号 S1_A1, S1_A2... |
| `anchors[].type` | entity / term / quantity / temporal / scope |
| `anchors[].text` | 干净表面文本（可去除纯填充） |
| `anchors[].evidence` | segment 内逐字连续证据 |
| `anchors[].importance` | 1=背景, 2=重要, 3=改变结论/行动/风险 |

## 2. Source Event 输出（Step 2）

```json
{
  "sample_id": "en2zh-01-tech_001",
  "source_events": [
    {
      "event_id": "S1_E1",
      "seg_id": "S1",
      "type": "judgment",
      "summary": "speaker is not sure whether that answers the question (negated, uncertainty stance)",
      "evidence": "so I'm not sure if that's getting it what you're asking?",
      "importance": 3
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `event_id` | 段内编号 S1_E1, S1_E2... |
| `seg_id` | 所属 segment |
| `type` | state / action / speech / judgment |
| `summary` | **核心字段**。一句完整中文缩句，承载所有语义信息（否定、情态、归因、语气等全部写进这句话）。这是 SI 匹配的主要依据 |
| `evidence` | 原文逐字连续句子 |
| `importance` | 1-3 |

## 3. Source Relation 输出（Step 3）

```json
{
  "sample_id": "en2zh-01-tech_001",
  "source_relations": [
    {
      "relation_id": "R1",
      "type": "attribution",
      "summary": "S2_E2 is attributed to Mark — the method description originates from Mark's speech",
      "evidence": "Mark mentioned looking at different metrics as a way to load balance across different servers",
      "source_event_ids": ["S2_E2"],
      "importance": 2
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `relation_id` | R1, R2... 连续编号 |
| `type` | cause_effect / condition / purpose / concession / contrast / temporal / elaboration / attribution / conclusion / progression / exemplification |
| `summary` | 一句中文描述关系 |
| `evidence` | 承载关系的原文片段 |
| `source_event_ids` | 涉及的 event ID 列表 |

## 4. Reference Align + Anchor 输出（Step 4）

```json
{
  "sample_id": "en2zh-01-tech_001",
  "reference_segments": [
    {
      "seg_id": "S1",
      "reference_text": "轮询负载均衡方案。不知道这是不是你想要的答案...",
      "anchors": [
        {
          "anchor_id": "S1_A1",
          "text": "轮询负载均衡方案",
          "evidence": "轮询负载均衡方案"
        }
      ]
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `reference_segments[].seg_id` | 与 source segment 相同 |
| `reference_segments[].reference_text` | 对齐后的 reference 文本，拼接 = reference_translation |
| `anchors[].anchor_id` | **必须与对应 source anchor 相同** |
| `anchors[].text` | reference 中的对应表达（无则为 ""） |
| `anchors[].evidence` | reference segment 内逐字证据（无则为 ""） |

**校验**：reference_segments 数量 = source_segments 数量；每个 segment 内 anchors 数量 = source anchors 数量。

## 5. Reference Event 输出（Step 5）

```json
{
  "sample_id": "en2zh-01-tech_001",
  "reference_events": [
    {
      "event_id": "S1_E1",
      "seg_id": "S1",
      "summary": "说话者不确定这是否回答了问题（否定，不确定语气）",
      "evidence": "不知道这是不是你想要的答案"
    }
  ]
}
```

**校验**：数量 = source_events 数量，event_id 一一匹配。

## 6. Reference Relation 输出（Step 6）

```json
{
  "sample_id": "en2zh-01-tech_001",
  "reference_relations": [
    {
      "relation_id": "R1",
      "preserved": true,
      "summary": "马克作为方法描述的来源，归属关系保留"
    }
  ]
}
```

**校验**：数量 = source_relations 数量。

## 7. 联合卡（Code Merge 后冻结）

```json
{
  "sample_id": "en2zh-01-tech_001",
  "source_text": "...",
  "reference_translation": "...",
  "segments": [
    {
      "seg_id": "S1",
      "source_text": "Round-robin um um load balancing scheme...",
      "reference_text": "轮询负载均衡方案...",
      "anchors": [
        {
          "anchor_id": "S1_A1",
          "type": "term",
          "source_text": "Round-robin load balancing scheme",
          "source_evidence": "Round-robin um um load balancing scheme",
          "reference_text": "轮询负载均衡方案",
          "reference_evidence": "轮询负载均衡方案",
          "importance": 3
        }
      ],
      "events": [
        {
          "event_id": "S1_E1",
          "seg_id": "S1",
          "type": "judgment",
          "source_summary": "speaker is not sure whether that answers the question (negated, uncertainty)",
          "source_evidence": "so I'm not sure if that's getting it...",
          "reference_summary": "说话者不确定这是否回答了问题（否定，不确定语气）",
          "reference_evidence": "不知道这是不是你想要的答案",
          "importance": 3
        }
      ]
    }
  ],
  "relations": [
    {
      "relation_id": "R1",
      "type": "attribution",
      "source_summary": "S2_E2 attributed to Mark",
      "source_evidence": "Mark mentioned...",
      "source_event_ids": ["S2_E2"],
      "reference_preserved": true,
      "reference_summary": "马克作为方法描述的来源，归属关系保留",
      "importance": 2
    }
  ],
  "flat_anchors": [...],
  "flat_events": [...],
  "flat_relations": [...],
  "metadata": {
    "protocol_version": "evisi_eval_v0.7",
    "joint_card_hash": "<sha256>"
  }
}
```

**合并逻辑**：
- `segments[].anchors[i]` = source.anchors[i] 的所有字段 + reference.anchors[i] 的 text/evidence
- `segments[].events[i]` = source.events[i] 的所有字段 + reference.events[i] 的 summary/evidence
- `relations[i]` = source.relations[i] 的所有字段 + reference.relations[i] 的 preserved/summary
- `flat_*` = 所有 segment 的 anchor/event 展平 + relations，方便 SI 匹配和评分遍历

## 8. SI Anchor Match 输出（Step 7）

```json
{
  "sample_id": "en2zh-01-tech_001",
  "si_segments": [
    {
      "seg_id": "S1",
      "si_text": "轮询负载均衡方案。我不确定这是否回答了你的问题..."
    }
  ],
  "anchor_matches": [
    {
      "anchor_id": "S1_A1",
      "match": "equivalent",
      "si_text": "负载均衡",
      "si_evidence": "负载均衡",
      "brief": "术语翻译正确"
    }
  ]
}
```

## 9. SI Event Match 输出（Step 8）

```json
{
  "sample_id": "en2zh-01-tech_001",
  "event_matches": [
    {
      "event_id": "S1_E1",
      "match": "equivalent",
      "si_summary": "说话者不确定是否回答了问题",
      "si_evidence": "我不确定这是否回答了你的问题",
      "brief": "否定和不确定性均保留"
    }
  ]
}
```

## 10. SI Relation Match 输出（Step 9）

```json
{
  "sample_id": "en2zh-01-tech_001",
  "relation_matches": [
    {
      "relation_id": "R1",
      "match": "equivalent",
      "si_evidence": "马克提到查看不同的指标...",
      "brief": "SI 保留了 Mark 作为方法描述来源的归属关系"
    }
  ]
}
```

match 取值：
- `equivalent` → 1.0
- `partial` → 0.5
- `contradiction` → 0.0
- `missing` → 0.0
- `uncertain` → 不进入分母
- `not_scored` → 不进入分母（仅 Relation，端点 Event 不可用）

## 11. 最终结果

```json
{
  "sample_id": "en2zh-01-tech_001",
  "system_name": "Doubao",
  "source_text": "...",
  "reference_translation": "...",
  "si_translation": "...",
  "joint_card_hash": "<sha256>",
  "si_segments": [...],
  "anchor_matches": [...],
  "event_matches": [...],
  "relation_matches": [...],
  "fluency_issues": [...],
  "si_expression_issues": [...],
  "dimension_scores": {
    "anchor_fidelity": 85.7,
    "event_fidelity": 92.3,
    "relation_fidelity": 100.0,
    "fluency": 100.0,
    "si_expression": 100.0
  },
  "final_score": 91.5,
  "score_status": "provisional",
  "score_diagnostics": {
    "anchor_fidelity": {
      "total_items": 8,
      "decided_items": 7,
      "uncertain_items": 1,
      "blocked_items": 0,
      "item_decisions": [...]
    }
  }
}
```
