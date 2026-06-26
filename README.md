# EviSI-Eval Agent

Evidence-driven evaluation for final simultaneous interpretation transcripts.

This repository implements v0.1 of the design:

- Build an `Evaluation Card` from source text.
- Verify key fact slots in a final SI transcript.
- Attribute each error to one dimension only.
- Apply fixed deductions and score caps.
- Export JSON/CSV/HTML reports.

The v0.1 scope is intentionally narrow: **fact accuracy + cap rules**. Proposition, relation, SI expression, and target-language quality hooks are present in the schema, but they are not scored yet.

## Quick Start

```powershell
cd D:\EviSI-Eval-Agent
python -m evisi_eval build-card --input data/raw_samples.jsonl --output data/cards.jsonl
python -m evisi_eval run-eval --cards data/cards.jsonl --outputs data/system_outputs.jsonl --output data/eval_results.jsonl
python -m evisi_eval export-report --input data/eval_results.jsonl --output reports/demo_report.html
```

No API key is required for the default rules-only mode. If `OPENAI_API_KEY` is configured later, the model verifier can be enabled in a future extension without changing the file formats.

## Runbooks

- English: [AGENT_RUNBOOK_EN.md](AGENT_RUNBOOK_EN.md)
- 中文: [AGENT_RUNBOOK_ZH.md](AGENT_RUNBOOK_ZH.md)

## Local API Key Setup

Do not hard-code API keys in source files. For local testing, copy:

```powershell
copy .\local_secrets.py.example .\local_secrets.py
```

Then edit `local_secrets.py` and set:

```python
OPENAI_API_KEY = "your-key"
```

`local_secrets.py` is ignored by git. You can test connectivity with:

```powershell
python -m evisi_eval check-api
```

## Data Formats

`raw_samples.jsonl`:

```json
{"sample_id":"s1","source_text":"Apple reported a 15% increase in revenue in Q2.","offline_translation":"苹果第二季度收入增长15%。","domain":"finance"}
```

`system_outputs.jsonl`:

```json
{"sample_id":"s1","system_name":"sys_a","si_translation":"谷歌第二季度收入增长了50%。"}
```

`cards.jsonl` contains `EvaluationCard` objects. You can manually edit these cards before running evaluation. The most important fields are `facts[]`, `allowed_omissions[]`, and `forbidden_losses[]`.

## Recommended v0.1 Workflow

1. Generate cards from source text.
2. Manually review facts and importance values for the pilot set.
3. Freeze reviewed cards.
4. Evaluate system outputs.
5. Inspect cap triggers and attributed errors.
6. Add missing aliases or acceptable variants to cards.

## Project Layout

- `evisi_eval/` - evaluator package.
- `schemas/` - JSON Schema contracts.
- `prompts/` - model prompt templates for later LLM-backed mode.
- `data/` - demo JSONL inputs.
- `reports/` - generated reports.
- `tests/` - lightweight smoke tests.

## Current Limitations

- v0.1 does not score propositions, relations, SI expression, or target-language acceptability.
- Rule extraction is conservative and should be corrected by human card review.
- Entity matching depends on `acceptable_variants` and alias data in the card.
- LLM confidence is not used in rules-only mode.
