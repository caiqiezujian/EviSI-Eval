# EviSI-Eval v0.5 标准化测试数据

- `source_00_input.jsonl`：全部源文，每个 sample 只出现一次。
- `target_00_input.jsonl`：全部同传最终译文。
- `samples/<sample_id>/`：按样本拆分，便于人工查看。
- `smoke/`：第一条源文和第一条系统译文，用于低成本端到端测试。

`system_asr` 不进入评测；`reference_translation` 仅保留在输入中，不传入核心评测阶段。
