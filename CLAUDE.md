# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

EviSI-Eval is an LLM-driven evaluation agent for simultaneous interpretation (SI) quality. Protocol version `evisi_eval_v0.5`, implementation version `0.5.0`.

**Core design constraint**: the LLM makes all semantic judgments; the code layer handles orchestration, structural validation, I/O, and deterministic computation. The code must never judge translation correctness.

The pipeline uses a **dual-model architecture**: a primary LLM and an independent reviewer LLM each judge the same evidence, then disagreements are adjudicated by a third call. Scoring is entirely deterministic based on the structured judgements.

**HTTP client**: uses Python `urllib` stdlib (no SDK required). Supports OpenAI-compatible and Gemini protocols. Hardcoded `temperature=0`, `response_format={"type":"json_object"}`. The `openai>=1.0.0` package is optional (for the `[llm]` extra only).

## Build, test, and run

```bash
# Install in editable mode
pip install -e ".[dev,llm]"

# Run all tests
python3 -m pytest -q

# Run a single test file
python3 -m pytest tests/test_agents.py -q

# Run a single test by name
python3 -m pytest tests/test_agents.py::test_source_card_build -q

# Run v0.5 validation tests
python3 -m pytest tests/test_protocol_v05.py -q

# Run pipeline integration tests
python3 -m pytest tests/test_pipeline.py -q
```

Tests use `ScriptedLLMClient` (in `evisi_eval/llm_provider.py`) — a deterministic, in-memory client with pre-baked JSON responses. **No API keys needed.** Test fixture helpers in `test_agents.py` return complete response dicts and are shared with `test_pipeline.py`.

## CLI entry points

```bash
# Full evaluation pipeline
python3 -m evisi_eval run --samples <samples.jsonl> --outputs <outputs.jsonl> --run-name my_run

# Run with independent reviewer model
python3 -m evisi_eval run --samples <samples.jsonl> --outputs <outputs.jsonl> \
  --provider openai --review-provider deepseek --run-name cross_model

# Prepare standardized input data
python3 -m evisi_eval prepare-data --samples data/user_samples.jsonl --outputs data/user_system_outputs.jsonl --output-dir data/user_samples_v03

# Verify provider connectivity and JSON compliance
python3 -m evisi_eval check-provider --provider deepseek

# Convert wide-format data to long-format JSONL
python3 -m evisi_eval import-data --input data/raw_zh.json data/raw_en.json \
  --samples-output data/samples.jsonl --outputs-output data/outputs.jsonl

# Smoke test (end-to-end on one sample)
.\scripts\run_smoke_deepseek.ps1   # Windows / PowerShell
```

Optional flags for `run`: `--resume` (hash-matched config guard), `--sample-id`, `--system-name`, `--limit-samples`, `--limit-outputs`.

## Architecture

### Data objects

Three core structures flow through the pipeline (JSON schemas in `schemas/`):

1. **`source_card`** — frozen once per sample. Contains `source_units`, `source_anchors`, `source_events`, `source_relations`. Its hash is cached; shared across all systems evaluating that sample.
2. **`target_eval_card`** — built per (sample, system). Contains `eval_units` (aligned segmentation), target anchors/events/relations, fluency issues, SI expression issues.
3. **`final_result`** — merged primary + reviewer judgements, adjudicated disagreements, deterministic dimension scores, weighted final score, and narrative summary.

### Agent model

The evaluation is decomposed into 9 LLM agents, each with a dedicated prompt file under `prompts/`:

| Agent class (in `agents.py`) | Prompt file | What it does |
|---|---|---|
| `SourceCardAgent` | `source_evidence_agent.md` | Segment source, extract anchors/events/relations. Runs once per sample. |
| `AlignmentAgent` | `alignment_agent.md` | Align target translation to source units. Runs per system. |
| `TargetEvidenceAgent` | `target_evidence_agent.md` | Extract target-side anchors/events/relations **without seeing source text**. |
| `FluencyAgent` | `fluency_agent.md` | Rate fluency, find disfluencies. Sees only the translation. |
| `SIExpressionAgent` | `si_expression_agent.md` | Evaluate SI-specific delivery issues. Sees source + translation. |
| `JudgeAgent` (primary) | `primary_judge_agent.md` | Judge source items against target evidence. |
| `JudgeAgent` (reviewer) | `reviewer_agent.md` | Independent re-judgement of the same evidence. |
| `AdjudicatorAgent` | `adjudicator_agent.md` | Resolve disagreements between primary and reviewer. |
| `SummaryAgent` | `summary_agent.md` | Write narrative summary from structured scores. |
| *(repair)* | `schema_repair.md` | Structural repair prompt, called when validation fails. |

### Agent trace structure

Every LLM call records: `{task, provider, model, request_id, usage}`. The `_canonicalize()` function in `agents.py` always injects `sample_id` and `system_name` from the payload into the LLM output, ensuring these keys survive repair/fallback.

### Call flow

```
run_pipeline (pipeline.py)
  └─ SourceCardAgent.build(sample)              → source_card (frozen, cached)
  └─ EvaluationAgentLoop.run(source_card, output)  — per (sample, system)
       ├─ AlignmentAgent.align(...)              → eval_units
       ├─ TargetEvidenceAgent.analyze(...)       → target anchors/events/relations
       ├─ FluencyAgent.evaluate(...)             → fluency issues + assessment
       ├─ SIExpressionAgent.evaluate(...)        → SI expression issues + assessment
       ├─ target_eval_card assembled
       ├─ JudgeAgent.judge(...) primary          → anchor/event/relation judgements
       ├─ JudgeAgent.judge(...) reviewer         → independent judgements
       ├─ _build_disagreement_cases(...)         → diff primary vs reviewer
       ├─ AdjudicatorAgent.adjudicate(...)       → resolve disagreements (if any)
       ├─ calculate_scores(...) deterministic    → dimension scores + final score
       └─ SummaryAgent.summarize(...)            → narrative summary
```

### Key modules

| Module | Role |
|---|---|
| `evisi_eval/agents.py` | `Runner` (LLM call + repair + fallback), 9 agent classes, `EvaluationAgentLoop`, disagreement builder, judgement merger |
| `evisi_eval/pipeline.py` | `run_pipeline` — file I/O, source_card caching, failure tracking, metrics computation, HTML report generation |
| `evisi_eval/validation.py` | Structural validators, ID scheme enforcement, `calculate_scores()` (deterministic weighted scoring), verdict sets, dimension constants |
| `evisi_eval/llm_provider.py` | `HTTPJSONClient` (OpenAI-compatible + Gemini, stdlib `urllib`), `ScriptedLLMClient` (tests), JSON parsing with markdown fence stripping |
| `evisi_eval/config.py` | `ProviderConfig` (protocol, api_key, model, base_url, timeout_seconds=180, max_retries=2); resolves from `local_secrets.py` then env vars |
| `evisi_eval/prompt_loader.py` | Maps 10 prompt names to `.md` files; returns SHA-256 manifest for run reproducibility |
| `evisi_eval/cli.py` | argparse CLI: `run`, `prepare-data`, `check-provider`, `import-data` |
| `evisi_eval/report.py` | `export_html_report` — standalone HTML with per-system aggregates and per-result detail sections |
| `evisi_eval/dataset.py` | `prepare_dataset` — validate and split user data into standardized v0.5 layout with smoke subset |
| `evisi_eval/importers.py` | Wide-format JSON to long-format JSONL conversion (`convert_wide_rows`) |
| `evisi_eval/io_utils.py` | `read_jsonl`, `write_jsonl`, `append_jsonl`, `read_json`, `write_json` |

### Runner failure strategy

Each `Runner.run()` call (`agents.py:43`) follows:
1. One LLM call with the agent prompt
2. Structural validation — if it passes, done
3. **1** repair attempt via `schema_repair.md` prompt, re-validated
4. If still failing, an optional deterministic fallback is applied
5. If fallback also fails, a `ValueError` is raised

## Prompt input isolation rules (critical)

- Source evidence agent sees **only** `source_text` — never any translation or reference.
- Alignment agent sees `source_units` + `si_translation` — the one bridge between source and target.
- Target evidence agent sees **only** `eval_unit_id` + `target_unit` — **never** `source_unit_ids` or source text.
- Fluency agent sees **only** `si_translation` — never source text.
- SI expression agent sees `source_text` + `si_translation` (needed to evaluate SI-specific delivery) — never reference translation.
- Primary/reviewer judges see `source_card` (source semantics only) + `target_eval_card` (target semantics + delivery issues) — never raw text.
- System names are passed as `"anonymous_system"`; real names are restored by code when writing outputs.
- Reference translations are **never** passed to any LLM agent.

## Scoring model

`calculate_scores()` in `validation.py:191` is fully deterministic:

- **Fidelity dimensions** (anchor/event/relation): weighted by source-item `importance` (1–3). Each judgement verdict maps to a numeric value via `VERDICT_VALUES`. Score = weighted earned / weighted decided, renormalized when a dimension has no source items.
- **Verdict sets differ by dimension**: anchors/events use `{correct, partially_correct, incorrect, missing, uncertain}`; relations use `{correct, weakened, incorrect, missing, uncertain}`.
- **Delivery dimensions** (fluency/si_expression): start at 100, deduct per-issue severity via `SEVERITY_DEDUCTIONS` (minor: 2, moderate: 6, major: 15, critical: 35). Same `target_span` cannot be deducted twice.
- **Score status**: `final` (all decided, confidence ≥ 0.60), `provisional_review_required` (uncertain or low-confidence items), or `provisional_no_decisions` (all fidelity items uncertain — score is `null`).
- **Final score**: weighted average across all applicable dimensions, with weights renormalized when a dimension is N/A.
- Constants in `validation.py`: `DIMENSION_WEIGHTS` (anchor:30, event:25, relation:20, fluency:15, si_expression:10), `VERDICT_VALUES`, `SEVERITY_DEDUCTIONS`, `MIN_FINAL_CONFIDENCE` (0.60).

## Configuration

API keys and model selection via `config.py:get_provider_config()`:
1. First checks `local_secrets.py` (git-ignored, from `local_secrets.py.example`)
2. Then environment variables

Provider env vars follow `{PROVIDER}_API_KEY`, `{PROVIDER}_MODEL`, `{PROVIDER}_BASE_URL`. The `custom` provider uses `EVISI_CUSTOM_*` prefix and `EVISI_CUSTOM_PROTOCOL`.

Additional env vars: `EVISI_PRIMARY_PROVIDER` (default provider name), `EVISI_REVIEW_PROVIDER` (separate reviewer, defaults to primary), `EVISI_TIMEOUT_SECONDS` (default 180), `EVISI_MAX_RETRIES` (default 2).

## Test patterns

Tests use `ScriptedLLMClient` which returns pre-baked JSON from an ordered list. Key patterns:

- **Response fixture helpers** in `test_agents.py` return complete dicts matching the expected schema for each agent (e.g. `source_response()`, `alignment_response()`).
- **Pipeline tests** (`test_pipeline.py`) construct `ScriptedLLMClient` with ordered response lists: `[source_response(), *per_output_responses(), *per_output_responses()]` for a 1-sample, 2-system run.
- **Validation tests** (`test_protocol_v05.py`) call validator functions directly with minimal in-line dicts, testing specific constraint violations.

## Output structure

```
results/<run_name>/
├── source/
│   ├── source_00_input.jsonl       # input samples (copied)
│   └── source_cards.jsonl          # frozen source cards
├── target/
│   ├── target_00_input.jsonl       # input outputs (copied)
│   └── target_eval_cards.jsonl     # per-system eval cards
├── score/
│   ├── score_01_primary_judgements.jsonl
│   ├── score_02_review_judgements.jsonl
│   ├── score_03_adjudications.jsonl
│   └── score_06_final_results.jsonl
├── agent_trace.jsonl               # all LLM calls with usage
├── failures.jsonl
├── metrics.json
├── run_manifest.json               # input/prompt/impl/score-config hashes
└── report.html                     # standalone HTML report
```

## Key design decisions

- **Evidence is always verbatim**: every `evidence_span`, `target_span` is validated to appear verbatim in the corresponding unit text.
- **Lossless segmentation**: source/target unit concatenation must equal the original text. Enforced by validators.
- **Every source_unit_id appears exactly once** across eval_units; source_unit_ids must be adjacent and ordered.
- **Sequential IDs**: items use sequential prefixed IDs (SA1, SE1, TA1, TE1, AJ1, EJ1, RJ1, F1, X1, SR1, TR1). Uniqueness and order validated.
- **Frozen source card**: source-card artifacts include a content hash (`source_card_hash`) and a `frozen_before_system_evaluation` flag.
- **Dual-model judgement**: primary and reviewer are independent LLM calls over the same evidence. Disagreements (different verdicts or confidence < 0.60) trigger an adjudication agent. If both agree, confidence is the minimum of the two.
- **No raw text in scoring**: scoring only consumes structured judgements, never raw source/translation text.
- **`src/` directory is stale**: contains only `__pycache__` artifacts from a previous version. Active code is in `evisi_eval/`.
