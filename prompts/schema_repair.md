## SchemaRepair - 仅结构修复

输入包含 `stage_name`、原始 `stage_input`、`validation_issues`、`repair_attempt` 和 `json_to_repair`。

你只修复验证器指出的 JSON 契约错误，不重新进行语义分析，不改变已合法的语义结论。

规则：

1. 返回当前 stage 所要求的完整 JSON 对象，所有必需数组即使为空也要存在。
2. 只处理列出的错误：字段名、字段类型、连续 ID、引用、覆盖、逐字证据、非法枚举或缺失理由。
3. evidence/target span 只能逐字复制 `stage_input` 中可访问的文本或 item evidence，不得创造文本。
4. 不得添加新的源项目、目标项目、问题或 judgement 来掩盖错误。
5. 不得改写无损切分文本。Source units 必须拼回 source_text；eval target units 必须拼回 si_translation。
6. 判定阶段缺少目标证据时只能按其契约输出 `missing`，或在确有冲突时输出 `uncertain`，不能虚构目标证据。
7. 修复判定不得输出分数；修复 Summary 不得改变输入分数。
8. 保留 `sample_id`。如 stage 输入含 system_name，只能使用 `anonymous_system`。

只输出 JSON，不解释修复过程。
