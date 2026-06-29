# 评分协议

五维分数均为 0 到 100：Anchor Fidelity、Event Fidelity、Relation Fidelity、Fluency、SI Expression。

内容三维只能依据对应 judgement 和已有全文复核说明。Fluency 与 SI Expression 只能依据对应 issue 和 assessment。同一错误不得跨维度重复惩罚。

权重固定为 30%、25%、20%、15%、10%。代码只执行：

```text
final_score =
anchor_fidelity * 0.30 +
event_fidelity * 0.25 +
relation_fidelity * 0.20 +
fluency * 0.15 +
si_expression * 0.10
```

若某一内容维没有源项目，该维度为 100，并说明无适用项目。`uncertain` 不伪装成正确或错误，必须在解释和最终总结中保留。
