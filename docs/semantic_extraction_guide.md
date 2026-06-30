# Anchor / Event / Relation 纯抽取指南

该脚本只运行三个阶段：

```text
1. SourceEvidenceAgent：源文无损切分 + Anchor/Event/Relation
2. AlignmentAgent：源单元与译文无损对齐
3. TargetEvidenceAgent：目标侧盲抽取 Anchor/Event/Relation
```

不会运行 Fluency、SI Expression、Primary Judge、Reviewer、Adjudicator、Summary 或评分。

## 运行一条数据

在 Anaconda Prompt 中：

```bat
cd /d D:\EviSI-Eval-Agent
conda activate evisi-eval

python scripts\run_semantic_extraction.py ^
  --samples data\user_samples_v05\smoke\source_00_input.jsonl ^
  --outputs data\user_samples_v05\smoke\target_00_input.jsonl ^
  --provider deepseek ^
  --output-dir results ^
  --run-name semantic_v2_smoke
```

单行写法：

```bat
python scripts\run_semantic_extraction.py --samples data\user_samples_v05\smoke\source_00_input.jsonl --outputs data\user_samples_v05\smoke\target_00_input.jsonl --provider deepseek --output-dir results --run-name semantic_v2_smoke
```

## 输出

```text
results/semantic_v2_smoke/
├── extraction_manifest.json
├── extraction_summary.json
├── failures.jsonl
├── source/
│   └── source_cards.jsonl
└── target/
    ├── alignments.jsonl
    └── target_semantic_cards.jsonl
```

重点比较：

- `source/source_cards.jsonl` 中的 source_anchors/source_events/source_relations；
- `target/target_semantic_cards.jsonl` 中的 target_anchors/target_events/target_relations；
- 问句、判断、言说在两侧是否得到一致 Event 类型；
- Relation 是否稀疏，是否存在把相邻、问答、话题延续误抽成关系的情况。

## 断点恢复

同一次 run 因网络失败后，可以使用完全相同的命令并增加：

```text
--resume
```

Source、Alignment、Target 分别落盘。Target 失败不会重新运行已成功的 Source 和 Alignment。

只要输入、模型、Prompt hash 或实现 hash 改变，resume 会拒绝继续，必须换新的 `run-name`。旧协议 Source/Target Card 缺少新的 Relation 依据字段，不能用于本协议。

不要把旧结果目录手工复制到新 `run-name`。`--resume` 必须找到由当前脚本生成且完全匹配的 `extraction_manifest.json`，并会重新验证三个阶段的缓存。
