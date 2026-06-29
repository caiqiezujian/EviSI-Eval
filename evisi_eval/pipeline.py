"""EviSI-Eval v0.4 — Agent-based evaluation pipeline.

Uses AgentLoop (SourceWorker → TargetWorker → MainAgent) instead of the
16-stage hardcoded pipeline. The file-level orchestration (reading inputs,
iterating samples/outputs, writing artifacts, generating reports) remains
the responsibility of this module.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

from .agents import PROTOCOL_VERSION, AgentLoop
from .config import get_provider_config
from .io_utils import append_jsonl, read_json, read_jsonl, write_json, write_jsonl
from .llm_provider import HTTPJSONClient, LLMClient
from .prompt_loader import prompt_manifest
from .report import export_html_report
from .validation import DIMENSIONS

# ── Artifact file layout ──
SOURCE_FILES = {
    "source_cards": "source/source_cards.jsonl",
}
TARGET_FILES = {
    "target_eval_cards": "target/target_eval_cards.jsonl",
}
SCORE_FILES = {
    "score_06_final_results": "score/score_06_final_results.jsonl",
}
ARTIFACT_FILES = {**SOURCE_FILES, **TARGET_FILES, **SCORE_FILES}


# ── Public API ──

def run_pipeline(
    samples_path: str,
    outputs_path: str,
    output_dir: str = "results",
    run_name: str = "evaluation_run",
    provider_name: str = "deepseek",
    resume: bool = False,
    sample_ids: list[str] | None = None,
    system_names: list[str] | None = None,
    limit_samples: int | None = None,
    limit_outputs: int | None = None,
    client: LLMClient | None = None,
) -> dict[str, Any]:
    """Run the agent-based evaluation pipeline.

    Args:
        samples_path: Path to source samples JSONL.
        outputs_path: Path to system output JSONL.
        output_dir: Root directory for run results.
        run_name: Name of this run (creates a subdirectory).
        provider_name: One of deepseek, openai, gemini, custom.
        resume: If True, skip already-completed samples.
        sample_ids: Optional whitelist of sample IDs to process.
        system_names: Optional whitelist of system names to process.
        limit_samples: Max number of samples to process.
        limit_outputs: Max number of outputs to process.
        client: Optional pre-configured LLMClient (used in tests).

    Returns:
        Metrics dict with aggregate scores and per-system breakdowns.
    """
    # ── Load and validate inputs ──
    all_samples = [_normalize_sample(row) for row in read_jsonl(samples_path)]
    all_outputs = [_normalize_output(row) for row in read_jsonl(outputs_path)]
    _validate_inputs(all_samples, all_outputs)
    samples, outputs = _select_rows(
        all_samples, all_outputs, sample_ids, system_names, limit_samples, limit_outputs,
    )

    if client is None:
        client = HTTPJSONClient(get_provider_config(provider_name))

    # ── Set up run directory ──
    run_dir = Path(output_dir) / run_name
    paths = {key: run_dir / value for key, value in ARTIFACT_FILES.items()}
    paths.update({
        "source_input": run_dir / "source/source_00_input.jsonl",
        "target_input": run_dir / "target/target_00_input.jsonl",
        "failures": run_dir / "failures.jsonl",
        "metrics": run_dir / "metrics.json",
        "manifest": run_dir / "run_manifest.json",
        "report": run_dir / "report.html",
        "agent_trace": run_dir / "agent_trace.jsonl",
    })
    run_dir.mkdir(parents=True, exist_ok=True)

    # ── Manifest and resume guard ──
    manifest = _manifest(samples_path, outputs_path, samples, outputs, client)
    if resume and paths["manifest"].exists():
        _assert_resume_compatible(read_json(paths["manifest"]), manifest)
    elif not resume:
        for path in paths.values():
            if path.suffix == ".jsonl":
                write_jsonl(path, [])
    write_json(paths["manifest"], manifest)
    write_jsonl(paths["source_input"], samples)
    write_jsonl(paths["target_input"], outputs)

    # ── Setup the agent loop ──
    loop = AgentLoop(client)

    # ── Resume state ──
    cards = {
        str(r["sample_id"]): r
        for r in (read_jsonl(paths["source_cards"]) if resume else [])
    }
    failures = read_jsonl(paths["failures"]) if resume else []
    results = read_jsonl(paths["score_06_final_results"]) if resume else []
    completed = {(str(r["sample_id"]), str(r["system_name"])) for r in results}

    # ── Sink helpers ──
    def source_sink(stage: str, artifact: dict[str, Any]) -> None:
        if stage == "source_cards":
            append_jsonl(paths["source_cards"], artifact)

    def target_sink(stage: str, artifact: dict[str, Any]) -> None:
        if stage == "target_eval_cards":
            append_jsonl(paths["target_eval_cards"], artifact)

    def score_sink(stage: str, artifact: dict[str, Any]) -> None:
        if stage == "score_06_final_results":
            append_jsonl(paths["score_06_final_results"], artifact)

    def trace_sink(artifact: dict[str, Any]) -> None:
        append_jsonl(paths["agent_trace"], artifact)

    # ── Main evaluation loop ──
    for output in outputs:
        key = (str(output["sample_id"]), str(output["system_name"]))
        if key in completed:
            continue

        sample = next(
            (s for s in samples if str(s["sample_id"]) == key[0]), None
        )
        if sample is None:
            failure = {
                "stage": "unknown_sample",
                "sample_id": key[0],
                "system_name": key[1],
                "error": "Output references a sample not in the input set",
            }
            failures.append(failure)
            append_jsonl(paths["failures"], failure)
            continue

        try:
            # AgentLoop handles source → target → score in one call
            final_result, _ = loop.run(
                sample, output,
                source_sink=source_sink,
                target_sink=target_sink,
                score_sink=score_sink,
            )
            results.append(final_result)
            completed.add(key)
            # Write trace
            trace_sink({
                "sample_id": key[0],
                "system_name": key[1],
                "agent_trace": final_result["metadata"]["agent_trace"],
            })
        except Exception as exc:
            failure = {
                "stage": "agent_loop",
                "sample_id": key[0],
                "system_name": key[1],
                "error": str(exc),
            }
            failures.append(failure)
            append_jsonl(paths["failures"], failure)

    # ── Finalize ──
    results.sort(key=lambda r: (str(r["sample_id"]), str(r["system_name"])))
    write_jsonl(paths["score_06_final_results"], results)
    metrics = compute_metrics(results, failures)
    metrics["paths"] = {key: str(p) for key, p in paths.items()}
    write_json(paths["metrics"], metrics)
    export_html_report(results, metrics, paths["report"])
    return metrics


def compute_metrics(
    results: list[dict[str, Any]],
    failures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[str(result["system_name"])].append(result)
    systems = {}
    for system_name, rows in sorted(grouped.items()):
        systems[system_name] = {
            "samples": len(rows),
            "average_score": _mean([float(r["final_score"]) for r in rows]),
            "dimension_scores": {
                dim: _mean([float(r["dimension_scores"][dim]) for r in rows])
                for dim in DIMENSIONS
            },
        }
    return {
        "protocol_version": PROTOCOL_VERSION,
        "num_results": len(results),
        "num_failures": len(failures or []),
        "average_score": _mean([float(r["final_score"]) for r in results]),
        "systems": systems,
    }


# ── Input normalization ──

def _normalize_sample(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": str(row.get("sample_id") or row.get("vid") or "").strip(),
        "source_text": str(row.get("source_text") or row.get("transcript") or ""),
        "reference_translation": row.get(
            "reference_translation", row.get("offline_translation")
        ),
        "src_lang": str(row.get("src_lang") or "unspecified"),
        "tgt_lang": str(row.get("tgt_lang") or "unspecified"),
        "domain": str(row.get("domain") or "unspecified"),
    }


def _normalize_output(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": str(row.get("sample_id") or row.get("vid") or "").strip(),
        "system_name": str(row.get("system_name") or "").strip(),
        "si_translation": str(row.get("si_translation") or ""),
    }


# ── Validation ──

def _validate_inputs(
    samples: list[dict[str, Any]], outputs: list[dict[str, Any]]
) -> None:
    sample_ids = [row["sample_id"] for row in samples]
    if any(not v for v in sample_ids) or len(sample_ids) != len(set(sample_ids)):
        raise ValueError("samples must have unique non-empty sample_id values")
    for row in samples:
        if not row["source_text"].strip():
            raise ValueError(f"sample {row['sample_id']} has empty source_text")
    valid_ids = set(sample_ids)
    output_keys = []
    for row in outputs:
        if row["sample_id"] not in valid_ids:
            raise ValueError(
                f"output references unknown sample_id={row['sample_id']}"
            )
        if not row["system_name"] or not row["si_translation"].strip():
            raise ValueError("every output needs system_name and si_translation")
        output_keys.append((row["sample_id"], row["system_name"]))
    if len(output_keys) != len(set(output_keys)):
        raise ValueError("outputs must have unique (sample_id, system_name) pairs")


def _select_rows(
    samples: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    sample_ids: list[str] | None,
    system_names: list[str] | None,
    limit_samples: int | None,
    limit_outputs: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected_samples = [
        r for r in samples if sample_ids is None or r["sample_id"] in set(sample_ids)
    ]
    if limit_samples is not None:
        selected_samples = selected_samples[:limit_samples]
    selected_ids = {r["sample_id"] for r in selected_samples}
    selected_outputs = [
        r for r in outputs
        if r["sample_id"] in selected_ids
        and (system_names is None or r["system_name"] in set(system_names))
    ]
    if limit_outputs is not None:
        selected_outputs = selected_outputs[:limit_outputs]
    required_ids = {r["sample_id"] for r in selected_outputs}
    selected_samples = [r for r in selected_samples if r["sample_id"] in required_ids]
    if not selected_samples or not selected_outputs:
        raise ValueError("selection produced no sample/output pairs")
    return selected_samples, selected_outputs


# ── Manifest ──

def _manifest(
    samples_path: str,
    outputs_path: str,
    samples: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    client: LLMClient,
) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "samples_sha256": _file_hash(samples_path),
        "outputs_sha256": _file_hash(outputs_path),
        "selected_sample_ids": [r["sample_id"] for r in samples],
        "selected_output_keys": [
            [r["sample_id"], r["system_name"]] for r in outputs
        ],
        "prompt_hashes": prompt_manifest(),
        "provider": client.provider_name,
        "model": client.model_name,
    }


def _assert_resume_compatible(
    existing: dict[str, Any], current: dict[str, Any]
) -> None:
    changed = [k for k, v in current.items() if existing.get(k) != v]
    if changed:
        raise ValueError(
            "Cannot resume because run configuration changed: " + ", ".join(changed)
        )


def _file_hash(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None
