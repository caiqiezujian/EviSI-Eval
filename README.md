# EviSI-Eval Agent

Evidence-driven evaluation for final simultaneous interpretation transcripts.

This repository implements v0.2 of the design:

- Build an `Evaluation Card` from a required source transcript.
- Verify key fact slots in a final SI transcript.
- Verify minimal proposition coverage so fact-light utterances such as "I go to work" are still evaluable.
- Attribute each error to one dimension only.
- Apply fixed deductions and score caps.
- Export JSON/CSV/HTML reports.

The v0.2 scope supports two modes:

- `reference_assisted`: transcript + offline translation + SI output.
- `source_only`: transcript + SI output.

The source transcript is mandatory. Without a transcript, the system cannot evaluate translation fidelity; it can only inspect target-language fluency.

## Quick Start

```powershell
cd D:\EviSI-Eval-Agent
python -m evisi_eval build-card --input data/raw_samples.jsonl --output data/cards.jsonl
python -m evisi_eval run-eval --cards data/cards.jsonl --outputs data/system_outputs.jsonl --output data/eval_results.jsonl
python -m evisi_eval export-report --input data/eval_results.jsonl --output reports/demo_report.html
```

Benchmark-style pipeline:

```powershell
python run_eval.py `
  --samples data/mode_demo_raw_samples.jsonl `
  --outputs data/mode_demo_system_outputs.jsonl `
  --run-name mode_demo
```

No API key is required for the default rules-only mode. If `OPENAI_API_KEY` is configured later, the model verifier can be enabled in a future extension without changing the file formats.

## Runbooks

- English: [AGENT_RUNBOOK_EN.md](AGENT_RUNBOOK_EN.md)
- 中文: [AGENT_RUNBOOK_ZH.md](AGENT_RUNBOOK_ZH.md)
- 评测协议说明: [EVALUATION_PROTOCOL_ZH.md](EVALUATION_PROTOCOL_ZH.md)

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
{"sample_id":"s1","transcript":"Apple reported a 15% increase in revenue in Q2.","offline_translation":"苹果第二季度收入增长15%。","domain":"finance"}
```

`system_outputs.jsonl`:

```json
{"sample_id":"s1","system_name":"sys_a","si_translation":"谷歌第二季度收入增长了50%。"}
```

`cards.jsonl` contains `EvaluationCard` objects. You can manually edit these cards before running evaluation. The most important fields are `facts[]`, `allowed_omissions[]`, and `forbidden_losses[]`.

## Legacy CLI Workflow

1. Generate cards from source text.
2. Manually review facts and importance values for the pilot set.
3. Freeze reviewed cards.
4. Evaluate system outputs.
5. Inspect cap triggers and attributed errors.
6. Add missing aliases or acceptable variants to cards.

## Recommended v0.2 Workflow

1. Treat `transcript` as required ground truth input.
2. Use `offline_translation` when available to enable `reference_assisted` scoring.
3. Fall back to `source_only` mode when no offline translation exists.
4. Review facts and propositions in the generated card.
5. Run `run_eval.py` to produce `results/<run-name>/evaluation_result/evisi_eval/`.
6. Inspect `metrics.json`, `bad_cases.jsonl`, `not_pass.jsonl`, and `report.html`.

## Attribution Policy

The evaluator follows a single-penalty rule. If a fact-layer error already explains a meaning loss, the proposition-layer verdict is kept for diagnostics but its deduction is suppressed. This prevents one wrong number, entity, polarity, or scope marker from being counted twice.

## Project Layout

- `evisi_eval/` - evaluator package.
- `schemas/` - JSON Schema contracts.
- `prompts/` - model prompt templates for later LLM-backed mode.
- `data/` - demo JSONL inputs.
- `reports/` - generated reports.
- `tests/` - lightweight smoke tests.

## Current Limitations

- v0.2 has a minimal proposition layer, but does not yet implement full proposition decomposition.
- v0.2 does not score relations, SI expression, or target-language acceptability.
- Rule extraction is conservative and should be corrected by human card review.
- Entity matching depends on `acceptable_variants` and alias data in the card.
- LLM confidence is not used in rules-only mode.
