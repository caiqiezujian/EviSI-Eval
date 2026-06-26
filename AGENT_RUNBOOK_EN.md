# EviSI-Eval Agent Runbook

This document explains how the current v0.1 agent runs from input data to final report.

## 1. Current Scope

The current agent is v0.1. It evaluates **key fact accuracy** in final simultaneous interpretation transcripts.

It does not yet score:

- core proposition coverage
- logic relation preservation
- SI expression adaptability
- target-language acceptability
- real latency or streaming delay

The design is deliberately conservative: first make the fact layer stable, then expand to the other dimensions.

## 2. Input Files

There are two required input files.

### Source Samples

Path:

```text
data/labeled_raw_samples.jsonl
```

Each line is one source sample:

```json
{
  "sample_id": "case_001",
  "source_text": "Apple reported a 15% increase in revenue in Q2.",
  "offline_translation": "苹果公司报告第二季度收入增长15%。",
  "domain": "finance"
}
```

Fields:

- `sample_id`: unique sample ID.
- `source_text`: original source text.
- `offline_translation`: reference translation used only to help build the card. It is not the scoring target.
- `domain`: optional domain label.

### System Outputs

Path:

```text
data/labeled_system_outputs.jsonl
```

Each line is one final SI output from one system:

```json
{
  "sample_id": "case_001",
  "system_name": "sys_b_entity_number_bad",
  "si_translation": "谷歌第二季度收入增长了50%。",
  "expected_label": "critical_fact_error",
  "expected_errors": ["entity_mismatch", "percentage_mismatch"],
  "label_notes": "Apple 被译成谷歌，15% 被译成 50%，应触发封顶。"
}
```

Fields:

- `sample_id`: must match a source sample.
- `system_name`: system name.
- `si_translation`: final SI transcript to evaluate.
- `expected_label`: optional human expected label for debugging.
- `expected_errors`: optional human expected error list.
- `label_notes`: optional notes.

## 3. Step 1 - Build Evaluation Cards

Command:

```powershell
python -m evisi_eval build-card `
  --input data/labeled_raw_samples.jsonl `
  --output data/labeled_cards.jsonl
```

What happens:

1. The agent reads each source sample.
2. Rule extractors find key fact slots: percentages, money, numbers, dates and times, entities, polarity, direction, scope, and modality.
3. The agent creates an `Evaluation Card`.
4. The card is written to `data/labeled_cards.jsonl`.

Important: in real use, humans should review cards before scoring. The card is the scoring contract.

## 4. Step 2 - Run Evaluation

Command:

```powershell
python -m evisi_eval run-eval `
  --cards data/labeled_cards.jsonl `
  --outputs data/labeled_system_outputs.jsonl `
  --output data/labeled_eval_results.jsonl
```

What happens:

1. The agent loads frozen Evaluation Cards.
2. For each system output, it checks every fact.
3. Each fact gets a verdict: `correct`, `incorrect`, `missing`, or `ambiguous`.
4. Each non-correct verdict becomes an attributed error.
5. Deductions are summed.
6. Cap rules are applied.
7. Final result JSON is written to `data/labeled_eval_results.jsonl`.

## 5. Scoring Logic

The full score starts from 100. In v0.1 only the fact dimension is active:

```text
fact_accuracy = 35 points
```

The final score is:

```text
final_score = min(100 - deductions, lowest_triggered_cap)
```

## 6. Cap Rules

Caps prevent a fluent but factually wrong SI output from receiving a high score.

| Trigger | Meaning | Cap |
|---|---|---:|
| `critical_entity_mismatch` | key subject/object changed | 60 |
| `critical_polarity_error` | negation or polarity lost | 60 |
| `critical_direction_error` | increase/decrease or approve/reject reversed | 60 |
| `critical_scope_error` | at least / at most / only / all distorted | 60 |
| `critical_number_time_value_error` | key number/date/money/time value wrong | 70 |
| `multiple_critical_facts` | two or more critical facts wrong | 55 |

## 7. Step 3 - Export Report

Command:

```powershell
python -m evisi_eval export-report `
  --input data/labeled_eval_results.jsonl `
  --output reports/labeled_demo_report.html
```

The report shows sample ID, system name, expected label, final score, cap reason, and attributed errors.

## 8. Current Labeled Demo Results

```text
case_001 sys_a_good                    score=100
case_001 sys_b_entity_number_bad       score=55 cap=critical_entity_mismatch
case_001 sys_c_missing_number          score=70 cap=critical_number_time_value_error

case_002 sys_a_good                    score=100
case_002 sys_b_polarity_bad            score=60 cap=critical_polarity_error
case_002 sys_c_missing_age             score=97

case_003 sys_a_good                    score=100
case_003 sys_b_scope_number_bad        score=60 cap=critical_scope_error
case_003 sys_c_missing_scope           score=60 cap=critical_scope_error
```

## 9. One-Command Demo

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_demo.ps1
```

## 10. API Key Setup

The current evaluation works without an API key because v0.1 is rules-only.

For future LLM verification, use:

```powershell
copy .\local_secrets.py.example .\local_secrets.py
```

Then edit `local_secrets.py`:

```python
OPENAI_API_KEY = "your-key"
```

Then test:

```powershell
python -m evisi_eval check-api
```

Do not paste the API key into chat, source code, or README files.

## 11. Where Each Part Lives

| Part | File |
|---|---|
| CLI commands | `evisi_eval/cli.py` |
| Evaluation Card builder | `evisi_eval/card_builder.py` |
| Fact verification | `evisi_eval/verifier.py` |
| Scoring and caps | `evisi_eval/aggregator.py` |
| Normalization rules | `evisi_eval/normalization.py` |
| HTML/CSV report export | `evisi_eval/report.py` |
| Data models | `evisi_eval/models.py` |
| API key loader | `evisi_eval/config.py` |
| API connectivity check | `evisi_eval/api_check.py` |
| Card schema | `schemas/evaluation_card.schema.json` |
| Fact verdict schema | `schemas/fact_verdict.schema.json` |
| Final score schema | `schemas/final_score.schema.json` |
| Annotation guide | `annotation_guideline_v1.md` |

## 12. How To Add New Cases

1. Add source text to `data/labeled_raw_samples.jsonl`.
2. Add three system outputs to `data/labeled_system_outputs.jsonl`.
3. Rebuild cards.
4. Review and edit cards if needed.
5. Run evaluation.
6. Export report.

Recommended source case design:

- one clean/good output
- one critical factual error
- one partial or missing-fact output

## 13. Known Limitations

- Rule extraction can still over-extract or under-extract facts.
- Human card review is required for serious evaluation.
- Current system does not yet use LLM semantic equivalence.
- Chinese number words are only partially supported.
- Proposition and relation layers are planned but not active.

## 14. Recommended Next Step

1. Add 30-50 real samples.
2. Manually review `Evaluation Card` facts and aliases.
3. Add LLM verifier only for ambiguous or high-risk cases.
4. Start v0.2 proposition and relation scoring after the fact layer is stable.

