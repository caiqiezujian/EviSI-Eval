# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

EviSI-Eval is an LLM-driven evaluation agent for simultaneous interpretation (SI) quality. The current version is **v0.7**.

**v0.7** (`evisi_eval_v0.7`): Source+Reference joint extraction with positional SI matching and deterministic scoring.

**Core design constraint**: the LLM makes all semantic judgments; the code layer handles orchestration, structural validation, I/O, and deterministic computation. The code must never judge translation correctness.

**HTTP client**: uses Python `urllib` stdlib (no SDK required). Supports OpenAI-compatible and Gemini protocols. Hardcoded `temperature=0`, `response_format={"type":"json_object"}`.

## Build, test, and run

```bash
# Install in editable mode
pip install -e ".[dev,llm]"

# Run all tests
python -m pytest -q

# Run a single test
python -m pytest tests/test_dataset.py -q
```

Tests use `ScriptedLLMClient` (in `evisi_eval/llm_provider.py`) — a deterministic, in-memory client with pre-baked JSON responses. **No API keys needed.**

## CLI entry points

```bash
# v0.7 full evaluation
python3 -m evisi_eval run --samples <samples.jsonl> --outputs <outputs.jsonl> --run-name my_run

# v0.7 offline input validation (no API call)
python3 -m evisi_eval check-input --samples <samples.jsonl> --outputs <outputs.jsonl>

# Verify provider connectivity
python3 -m evisi_eval check-provider --provider deepseek

# Prepare standardized input data
python3 -m evisi_eval prepare-data --samples data/user_samples.jsonl --outputs data/user_system_outputs.jsonl --output-dir data/user_samples_v03

# Convert wide-format to long-format JSONL
python3 -m evisi_eval import-data --input data/raw_zh.json data/raw_en.json \
  --samples-output data/samples.jsonl --outputs-output data/outputs.jsonl
```

Optional flags for `run`: `--resume` (hash-matched config guard), `--sample-id`, `--system-name`, `--limit-samples`, `--limit-outputs`, `--provider` (deepseek/openai/gemini/custom), `--output-dir`.

## Architecture

### v0.7 Design

v0.7 uses **joint extraction + positional matching**: Source and Reference are extracted together into a frozen Joint Card (8 LLM calls). SI systems then match positionally against the frozen Joint Card (6 LLM calls per system). Arrays are aligned by index (source[i] ↔ reference[i] ↔ si[i]), not by ID cross-references.

**One frozen Joint Card per sample**, shared across all SI systems:

Source side (4 LLM calls):
1. **Source Segments** — segment source text (~2 sentences each)
2. **Source Anchors** — typed anchors (entity/term/quantity/temporal/scope) with importance 1-3
3. **Source Events** — structured events with predicate/semantic role arguments
4. **Source Relations** — relations between events (cause_effect, temporal_sequence, etc.)

Reference side (4 LLM calls):
5. **Reference Align** — align reference translation to source segments
6. **Reference Anchors** — position-corresponding reference anchor expressions
7. **Reference Events** — position-corresponding reference event expressions
8. **Reference Relations** — position-corresponding reference relation expressions

The Joint Card is assembled by Python via positional zip of source + reference arrays. Frozen with `joint_card_hash`.

**Per-system** (6 LLM calls): SI Align + SI Anchor Match + SI Event Match + SI Relation Match + Fluency + SI Expression → deterministic scoring.

**Key v0.7 design rules**:
- Source is the only semantic authority; Reference is auxiliary.
- SI ≠ Reference is never automatically an error. SI matching Source in a different way → equivalent.
- Positional array alignment: source[i] ↔ reference[i] ↔ si[i], not ID cross-references.
- No protocol injection — all prompts are self-contained.
- Flat JSON output — no nested component_results, operators grids, or hard_requirement structures.
- No accepted/rejected form lists — only single required forms where justified.

### v0.7 Call flow (14 phases)

```
Sample-level (shared across all systems):
  Phase 1   v07_source_segment        → source_segments
  Phase 2   v07_source_anchor         → source_anchors
  Phase 3   v07_source_event          → source_events
  Phase 4   v07_source_relation       → source_relations
  Phase 5   v07_reference_align       → reference_segments (aligned to source)
  Phase 6   v07_reference_anchor      → reference_anchors
  Phase 7   v07_reference_event       → reference_events
  Phase 8   v07_reference_relation    → reference_relations
            ☑ Joint Card assembled (Python zip) + frozen

Per-sample × system:
  Phase 9   v07_si_align              → si_segments (aligned to source)
  Phase 10  v07_si_anchor_match       → anchor_matches (positional)
  Phase 11  v07_si_event_match        → event_matches (positional)
  Phase 12  v07_si_relation_match     → relation_matches (positional)
  Phase 13  FluencyAgent              → fluency issues
  Phase 14  SIExpressionAgent         → SI expression issues
            ☑ Python deterministic scoring
```

### Agent prompts (v0.7)

15 prompt files under `prompts/` (12 v07_* + 3 shared):

| Prompt name | File | Role |
|---|---|---|
| `v07_source_segment` | `source/v07_source_segment.md` | Segment source text (~2 sentences) |
| `v07_source_anchor` | `source/v07_source_anchor.md` | Extract source anchors with type + importance |
| `v07_source_event` | `source/v07_source_event.md` | Extract events with predicate + arguments |
| `v07_source_relation` | `source/v07_source_relation.md` | Extract relations between events |
| `v07_reference_align` | `reference/v07_reference_align.md` | Align reference translation to source segments |
| `v07_reference_anchor` | `reference/v07_reference_anchor.md` | Position-corresponding ref anchor expressions |
| `v07_reference_event` | `reference/v07_reference_event.md` | Position-corresponding ref event expressions |
| `v07_reference_relation` | `reference/v07_reference_relation.md` | Position-corresponding ref relation expressions |
| `v07_si_align` | `si/v07_si_align.md` | Align SI translation to source segments |
| `v07_si_anchor_match` | `si/v07_si_anchor_match.md` | Match SI against joint anchors (positional) |
| `v07_si_event_match` | `si/v07_si_event_match.md` | Match SI against joint events (positional) |
| `v07_si_relation_match` | `si/v07_si_relation_match.md` | Match SI against joint relations (positional) |
| `fluency_agent` | `fluency_agent.md` | Evaluate SI fluency (Phase 13) |
| `si_expression_agent` | `si_expression_agent.md` | Evaluate SI expression quality (Phase 14) |
| `schema_repair` | `schema_repair.md` | Structural repair (shared by all agents) |

### Key modules

| Module | Role |
|---|---|
| `evisi_eval/v07_agents.py` | `V07JointCardBuilder` (phases 1-8), `V07SIMatcher` (phases 9-14) |
| `evisi_eval/v07_pipeline.py` | `run_v07_pipeline()` — orchestration, stage-level caching, resume, metrics, `check_v07_input_files()` |
| `evisi_eval/v07_validation.py` | All validators, `calculate_v07_scores()`, dimension weights, status values |
| `evisi_eval/agents.py` | `Runner` (LLM call + repair + fallback), `FluencyAgent`, `SIExpressionAgent`, `StageResult` |
| `evisi_eval/llm_provider.py` | `HTTPJSONClient` (OpenAI + Gemini, stdlib `urllib`), `ScriptedLLMClient` (tests) |
| `evisi_eval/config.py` | `ProviderConfig` (protocol, api_key, model, base_url, timeout_seconds=180, max_retries=2) |
| `evisi_eval/prompt_loader.py` | Maps prompt names to `.md` files; SHA-256 manifest for reproducibility |
| `evisi_eval/dataset.py` | `prepare_dataset()` — split a wide-format input into per-sample v0.7 directories |
| `evisi_eval/importers.py` | `import_wide_files()` — convert wide-format JSON/JSONL into v0.7 inputs |
| `evisi_eval/cli.py` | argparse CLI: `run`, `check-input`, `check-provider`, `prepare-data`, `import-data` |
| `evisi_eval/io_utils.py` | `read_jsonl`, `write_jsonl`, `append_jsonl`, `read_json`, `write_json` |

### Runner failure strategy

Each `Runner.run()` call:
1. One LLM call with the agent prompt
2. Structural validation — if it passes, done
3. Up to `MAX_REPAIR_ATTEMPTS=2` repair attempts via `schema_repair.md`
4. If still failing + fallback exists → use fallback
5. If no fallback → raise `ValueError`

### Stage-level caching

Each of the 14 phases caches its result individually under `<stage_dir>/0X_<stage_name>.json`. Resume reuses cached stages when the stage input hash matches. This means:
- Joint card stages (1-8) survive independently
- SI match stages (9-14) survive independently
- A failed SI match only re-runs stages 9-14 for that system, not the shared joint card

### v0.7 Scoring model

`calculate_v07_scores()` in `v07_validation.py` is fully deterministic:

- **Fidelity dimensions** (anchor/event/relation): each source item → one match. `match` value maps via `STATUS_VALUES`. Weighted by `importance` (1-3).
  - `equivalent` = 1.0, `partial` = 0.5, `contradiction`/`missing` = 0.0, `uncertain`/`not_scored` = excluded from denominator.
- **Relation dependency blocking**: if an endpoint event is missing/uncertain, the relation is `not_scored` (not double-penalized).
- **Delivery dimensions** (fluency/si_expression): start at 100, deduct per-issue severity (minor:2, moderate:6, major:15, critical:35). Same `target_span` cannot be deducted twice.
- **Score status**: `final`, `provisional_review_required` (uncertain items), `provisional_no_decisions` (all fidelity items uncertain → score=`null`).
- **Dimension weights**: anchor:35, event:35, relation:10, fluency:12, si_expression:8.

## Prompt input isolation (v0.7)

- Source Segment/Anchor/Event/Relation agents see **only** source text/segments — never any translation.
- Reference agents see source card + reference translation — the Reference is extracted positionally, not projected.
- SI agents see joint card + SI translation. Reference expressions are presented as auxiliary (not gold standard).
- Fluency agent sees **only** SI translation.
- SI Expression agent sees source text + SI translation.
- System names are `"anonymous_system"`; real names restored by code.
- All agents are prohibited from outputting scores.

## Test patterns

- **v0.7 pipeline tests**: fixture helpers return complete dicts per stage. Construct a `ScriptedLLMClient` with 14 ordered responses and validate the full pipeline.
- Tests are in `tests/` directory.

## Configuration

Provider config via `config.py:get_provider_config()`:
1. `local_secrets.py` (git-ignored, from `local_secrets.py.example`)
2. Environment variables: `{PROVIDER}_API_KEY`, `{PROVIDER}_MODEL`, `{PROVIDER}_BASE_URL`

The `custom` provider uses `EVISI_CUSTOM_*` prefix and `EVISI_CUSTOM_PROTOCOL`. Env vars: `EVISI_PRIMARY_PROVIDER`, `EVISI_TIMEOUT_SECONDS` (default 180), `EVISI_MAX_RETRIES` (default 2).

## Output structure (v0.7)

```
results/<run_name>/
├── joint/joint_cards_v07.jsonl          # frozen joint cards
├── joint/stages/<sample_id>/            # per-stage cached results (phases 1-8)
├── joint/source_00_input.jsonl          # input samples
├── target/si_cards_v07.jsonl            # SI match cards
├── target/stages/<sample_id>/<system>/  # per-stage cached results (phases 9-14)
├── target/target_00_input.jsonl         # input outputs
├── score/final_results_v07.jsonl        # final scores
├── failures.jsonl
├── metrics_v07.json
└── run_manifest_v07.json
```

## Key design decisions

- **Source is the only semantic authority.** Reference is auxiliary. SI ≠ Reference is not an automatic error.
- **Positional alignment.** Source[i] ↔ Reference[i] ↔ SI[i] via array indices, not ID cross-references. Validated by array length equality.
- **Evidence is always verbatim.** Every `source_evidence`, `reference_evidence`, and `si_evidence` is validated to appear verbatim in its corresponding segment text.
- **Lossless segmentation.** Source segment concatenation must equal the original source text. Same for reference and SI alignment.
- **Self-contained prompts.** No protocol injection — each prompt is fully self-contained with all rules, examples, and output schema.
- **Flat JSON output.** No nested component_results, operators grids, or hard_requirement structures. Simple arrays of flat objects.
- **Sequential IDs.** All item IDs use sequential prefixed numbering (S1, SA1, SE1, SR1, etc.). Uniqueness and order enforced by validators.
- **Frozen cards with content hashes.** Joint Card includes a SHA-256 hash of all fields except `metadata`. Resume validates hash match before reusing.
- **No dual-model review.** v0.7 uses single-pass matching (simpler, faster). No primary+reviewer+adjudicator pattern.
- **`src/` directory is stale.** Active code is in `evisi_eval/`.
