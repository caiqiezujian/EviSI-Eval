# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

EviSI-Eval is an LLM-driven evaluation agent for simultaneous interpretation (SI) quality. It takes a source transcript and an SI system's final output, then produces a five-dimension, evidence-backed score through a 16-stage chained pipeline. The protocol version is `evisi_eval_v0.3`.

Core design constraint: the LLM makes all semantic judgments; the code layer only handles orchestration, structural validation, I/O, and deterministic computation. The code must never judge translation correctness.

## Build, test, and run

```bash
# Install in editable mode
pip install -e ".[dev,llm]"

# Run all tests (8 tests, ~0.15s via ScriptedLLMClient — no network)
python -m pytest -q

# Run a single test file
python -m pytest tests/test_pipeline.py -q

# Run a single test by name
python -m pytest tests/test_pipeline.py::test_pipeline_writes_every_stage_and_hides_system_name -q
```

Tests use `ScriptedLLMClient` (defined in `evisi_eval/llm_provider.py:136`) — a deterministic, in-memory client that consumes a pre-baked list of JSON responses. No real API keys are needed for tests.

## CLI entry points

```bash
# Full evaluation pipeline
python -m evisi_eval run --samples <samples.jsonl> --outputs <outputs.jsonl> --provider deepseek --run-name my_run

# Prepare standardized v0.3 data from user samples
python -m evisi_eval prepare-data --samples data/user_samples.jsonl --outputs data/user_system_outputs.jsonl --output-dir data/user_samples_v03

# Verify provider connectivity and JSON compliance
python -m evisi_eval check-provider --provider deepseek

# Convert wide-format data (one row = one sample with many _trans columns) to long format
python -m evisi_eval import-data --input data/raw_zh.json data/raw_en.json --samples-output data/samples.jsonl --outputs-output data/outputs.jsonl
```

Resume a failed run with `--resume` (uses manifest hash matching to detect config changes). Filter with `--sample-id`, `--system-name`, `--limit-samples`, `--limit-outputs`.

## Architecture

Three core data objects flow through the pipeline (`docs/requirements-v0.3.md`):

1. **`source_card`** — built once per sample. Contains `source_units`, `source_anchors`, `source_events`, `source_relations`. Shared across all systems evaluating that sample.
2. **`target_eval_card`** — built once per (sample, system) pair. Contains `eval_units` (aligned segmentation), target-side anchors/events/relations, fluency issues, SI expression issues.
3. **`final_result`** — contains all judgements, global review, five dimension scores, weighted total, and summary.

Pipeline phases (`pipeline.py` → `agent.py`):

- **Source side** (steps 1–4, `build_source_card`): segmentation → anchor extraction → event extraction → relation extraction. Runs once per sample.
- **Target side** (steps 5–10, `evaluate_system` first half): aligned segmentation → target anchor/event/relation extraction → fluency evaluation → SI expression evaluation. Runs per system.
- **Scoring side** (steps 11–16, `evaluate_system` second half): anchor/event/relation judgement → global review → dimension scoring → final summary. Runs per system.

### Key modules

| Module | Role |
|---|---|
| `evisi_eval/agent.py` | `StageRunner` (orchestrates one LLM call + up to 2 repair attempts + fallback) and the two top-level functions `build_source_card` / `evaluate_system` |
| `evisi_eval/pipeline.py` | `run_pipeline` — file-level orchestration: reads inputs, manages source_card cache, iterates over outputs, calls `build_source_card` and `evaluate_system`, writes all artifacts, generates report |
| `evisi_eval/validation.py` | Structural validation functions for every stage. All live here — validates IDs, verbatim evidence spans, lossless concatenation, verdict sets, score ranges. Defines `DIMENSION_WEIGHTS` and `weighted_score()` |
| `evisi_eval/llm_provider.py` | `HTTPJSONClient` (OpenAI-compatible + Gemini via `urllib`), `ScriptedLLMClient` (for tests), and `parse_json_object` with markdown fence stripping |
| `evisi_eval/config.py` | `get_provider_config` — reads from `local_secrets.py` first, then env vars. Supports deepseek, openai, gemini, and custom providers |
| `evisi_eval/prompt_loader.py` | Maps 16 stage names + `schema_repair` to `.md` files under `prompts/`. Returns SHA-256 manifest for run reproducibility |
| `evisi_eval/cli.py` | argparse-based CLI with `run`, `prepare-data`, `check-provider`, `import-data` subcommands |
| `evisi_eval/dataset.py` | `prepare_dataset` — normalizes samples/outputs, creates per-sample directories, generates a smoke subset |
| `evisi_eval/importers.py` | `import_wide_files` — converts wide-format JSON/JSONL (one row per sample with `*_trans` columns) to long-format sample + output JSONL files |
| `evisi_eval/report.py` | Generates standalone HTML report with system-level aggregate table and per-result detail sections |
| `evisi_eval/io_utils.py` | `read_jsonl`, `write_jsonl`, `append_jsonl`, `read_json`, `write_json` |

### Call flow (single sample × system)

```
run_pipeline (pipeline.py)
  ├─ build_source_card (agent.py) — once per sample
  │    ├─ StageRunner.run("source_sentence_segmentation") → source_01_units
  │    ├─ StageRunner.run("source_anchor_extraction")    → source_02_anchors
  │    ├─ StageRunner.run("source_event_extraction")     → source_03_events
  │    └─ StageRunner.run("source_relation_extraction")  → source_04_relations
  │
  └─ evaluate_system (agent.py) — per system
       ├─ StageRunner.run("target_aligned_segmentation")   → target_01_eval_units
       ├─ StageRunner.run("target_anchor_extraction")      → target_02_anchors
       ├─ StageRunner.run("target_event_extraction")       → target_03_events
       ├─ StageRunner.run("target_relation_extraction")    → target_04_relations
       ├─ StageRunner.run("fluency_evaluation")            → target_05_fluency
       ├─ StageRunner.run("si_expression_evaluation")      → target_06_si_expression
       ├─ ... target_eval_card assembled ...
       ├─ StageRunner.run("anchor_judgement")              → score_01_anchor_judgements
       ├─ StageRunner.run("event_judgement")               → score_02_event_judgements
       ├─ StageRunner.run("relation_judgement")            → score_03_relation_judgements
       ├─ StageRunner.run("global_fidelity_review")        → score_04_global_review
       ├─ StageRunner.run("dimension_scoring")             → score_05_dimension_scores
       └─ StageRunner.run("final_summary")                 → score_06_final_results
```

## Prompt input isolation rules (critical)

When modifying prompts or the agent code, respect these isolation constraints:

- Source segmentation/anchor/event extraction sees **only** `source_text` or `source_units` — never any translation.
- Target anchor/event extraction sees **only** `eval_unit_id` + `target_unit` — never `source_unit_ids` or source text.
- Target relation extraction sees **only** `target_units` + `target_events` — never source content.
- Fluency sees **only** the complete `si_translation` — never source text.
- Dimension scoring sees **only** structured judgements/issues/review — never raw source or translation text.
- System names are passed to the LLM as `"anonymous_system"`; real names are restored by code when writing outputs.
- Reference translations are **never** passed to core evaluation stages.

## Stage runner failure strategy

Each `StageRunner.run()` call (`agent.py:43`) follows this sequence:
1. One LLM call with the stage prompt
2. Structural validation — if it passes, done
3. Up to 2 repair attempts via `schema_repair.md` prompt, each re-validated
4. If still failing, a deterministic fallback function is applied (e.g., salvage items with valid evidence spans, or collapse to a single unit)
5. If even the fallback fails validation, a `ValueError` is raised

## Configuration

API keys and model selection are resolved via `config.py:get_provider_config()`:
1. First checks `local_secrets.py` (git-ignored, derived from `local_secrets.py.example`)
2. Then checks environment variables (e.g., `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`)

Provider env vars follow the pattern `{PROVIDER}_API_KEY`, `{PROVIDER}_MODEL`, `{PROVIDER}_BASE_URL`. The `custom` provider uses `EVISI_CUSTOM_*` prefix.

## Key design decisions

- **Evidence is always verbatim**: every `evidence_span` in anchors, events, relations, and issue `target_span` values is validated to appear verbatim in the corresponding source/target unit text.
- **Lossless segmentation**: `source_units` concatenated must equal `source_text`; `target_units` concatenated must equal `si_translation`. Enforced by validators.
- **Sequential IDs**: all item IDs (SA1, SA2, TE1, TE2, etc.) are validated to be unique and sequential starting from 1.
- **No new errors in scoring**: Step 15 (dimension scoring) and Step 16 (final summary) must only consume preceding structured results, never re-read raw text.
- **`src/` directory is stale**: contains only `__pycache__` artifacts from a previous version. All active code is in `evisi_eval/`.
