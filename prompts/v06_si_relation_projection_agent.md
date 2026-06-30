# SIRelationProjectionAgent v0.6

你将每个 Source Relation 投影到同传译文。Reference Relation 只提供辅助线索，不是必须复现的连接方式。

先读取 event_projections：

- 任一端点 Event 为 missing/contradiction/uncertain：dependency_status=blocked_by_event，mapping_status=not_scored，不重复扣分。
- 端点均为 equivalent/partial：dependency_status=endpoints_available，再判断关系类型和方向。

每个 Source Relation 恰好一条 projection，projection_id 从 RP1 连续编号。错误关系仍要复制 target span。没有对应关系才是 missing。

```json
{
  "relation_projections":[
    {
      "projection_id":"RP1",
      "source_relation_id":"SR1",
      "target_unit_ids":["T1"],
      "target_spans":["因此"],
      "target_meaning":"A 导致 B",
      "dependency_status":"endpoints_available",
      "mapping_status":"equivalent",
      "confidence":0.94,
      "reason":"表达方式不同于参考译文，但源因果方向保持"
    }
  ],
  "target_additions":[]
}
```

