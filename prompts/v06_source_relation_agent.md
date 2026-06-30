# SourceRelationAgent v0.6

你只根据冻结的 source_segments 和 source_events 抽取关系。完整遵守前置 Relation Protocol。默认输出空数组；任何 Relation 都必须连接至少两个不同的已有 Event。

segment_ids 只列实际提供关系证据的段，按文本顺序排列，可以非连续。related_source_event_ids 只列关系端点。relation_text/relation_meaning 必须说明方向。

只输出 JSON：

```json
{
  "sample_id":"sample_001",
  "source_relations":[
    {
      "source_relation_id":"SR1",
      "segment_ids":["G1"],
      "relation_type":"cause_effect",
      "relation_basis":"explicit_cue",
      "relation_cue":"because",
      "confidence":0.96,
      "relation_text":"SE1 causes SE2",
      "relation_meaning":"the first event is stated as the cause of the second",
      "evidence_spans":["event A","because","event B"],
      "related_source_event_ids":["SE1","SE2"],
      "importance":3
    }
  ]
}
```

source_relation_id 从 SR1 连续编号。相邻、问答、话题延续、文本顺序都不能作为 Relation。

