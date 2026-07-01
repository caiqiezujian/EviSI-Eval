"""Orchestration for the v0.7 joint-card protocol.

14-phase pipeline:
  8 LLM calls for Joint Card (Source 4 + Reference 4) → frozen
  6 LLM calls per SI system (align + 3 matches + fluency + expression)
  Python deterministic scoring
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

from .config import get_provider_config
from .io_utils import append_jsonl, read_json, read_jsonl, write_json, write_jsonl
from .llm_provider import HTTPJSONClient, LLMClient
from .prompt_loader import prompt_manifest
from .v07_agents import (
    V07JointCardBuilder,
    V07SIMatcher,
    artifact_hash,
)
from .v07_validation import DIMENSION_WEIGHTS_V07, PROTOCOL_VERSION_V07

IMPLEMENTATION_VERSION_V07 = "0.7.0"
V07_PROMPTS = tuple(
    name for name in prompt_manifest()
    if name.startswith("v07_")
)


def run_v07_pipeline(
    samples_path: str,
    outputs_path: str,
    output_dir: str = "results",
    run_name: str = "v07_evaluation",
    provider_name: str = "deepseek",
    resume: bool = False,
    sample_ids: list[str] | None = None,
    system_names: list[str] | None = None,
    limit_samples: int | None = None,
    limit_outputs: int | None = None,
    client: LLMClient | None = None,
) -> dict[str, Any]:
    """Run the full v0.7 joint-card evaluation pipeline."""
    samples = [_normalize_sample(row) for row in read_jsonl(samples_path)]
    outputs = [_normalize_output(row) for row in read_jsonl(outputs_path)]
    _validate_inputs(samples, outputs)
    samples, outputs = _select_rows(
        samples, outputs, sample_ids, system_names, limit_samples, limit_outputs,
    )
    if client is None:
        client = HTTPJSONClient(get_provider_config(provider_name))

    run_dir = Path(output_dir) / run_name
    paths = {
        "joint_cards": run_dir / "joint/joint_cards_v07.jsonl",
        "si_cards": run_dir / "target/si_cards_v07.jsonl",
        "results": run_dir / "score/final_results_v07.jsonl",
        "source_input": run_dir / "joint/source_00_input.jsonl",
        "target_input": run_dir / "target/target_00_input.jsonl",
        "failures": run_dir / "failures.jsonl",
        "manifest": run_dir / "run_manifest_v07.json",
        "metrics": run_dir / "metrics_v07.json",
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("joint", "target", "score"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)

    manifest = _manifest(samples_path, outputs_path, samples, outputs, client)
    if resume:
        if not paths["manifest"].exists():
            raise ValueError("Cannot resume v0.7 run without run_manifest_v07.json")
        _assert_resume_compatible(read_json(paths["manifest"]), manifest)
    else:
        for path in paths.values():
            if path.suffix == ".jsonl":
                write_jsonl(path, [])
    write_json(paths["manifest"], manifest)
    write_jsonl(paths["source_input"], samples)
    write_jsonl(paths["target_input"], outputs)

    failures = read_jsonl(paths["failures"]) if resume else []
    joint_cards = {
        str(row.get("sample_id")): row
        for row in (read_jsonl(paths["joint_cards"]) if resume else [])
    }
    si_card_rows = read_jsonl(paths["si_cards"]) if resume else []
    si_cards = {
        (str(row.get("sample_id")), str(row.get("system_name"))): row
        for row in si_card_rows
    }
    results = read_jsonl(paths["results"]) if resume else []
    completed = {
        (str(row.get("sample_id")), str(row.get("system_name"))) for row in results
    }

    if resume:
        _validate_resume_joint_cards(samples, joint_cards)

    joint_builder = V07JointCardBuilder(client)
    si_matcher = V07SIMatcher(client)

    # ── Phase 1-8: Build joint cards (one per sample) ──────────────
    for sample in samples:
        sample_id = sample["sample_id"]
        if sample_id in joint_cards:
            continue
        try:
            card, _ = joint_builder.build(
                sample,
                stage_cache_dir=run_dir / "joint" / "stages" / sample_id,
                resume=resume,
            )
            joint_cards[sample_id] = card
            append_jsonl(paths["joint_cards"], card)
            failures = _remove_failure(failures, "joint", sample_id, None)
        except Exception as exc:
            failures.append({
                "stage": "joint", "sample_id": sample_id, "error": str(exc),
            })

    # ── Phase 9-14: Evaluate each SI system ────────────────────────
    for output in outputs:
        sample_id = output["sample_id"]
        system_name = output["system_name"]
        key = (sample_id, system_name)
        if key in completed:
            continue
        joint_card = joint_cards.get(sample_id)
        if joint_card is None:
            failures.append({
                "stage": "si", "sample_id": sample_id, "system_name": system_name,
                "error": "joint card unavailable — check joint-stage failures",
            })
            continue
        try:
            result, si_card = si_matcher.evaluate(
                joint_card,
                output,
                stage_cache_dir=(
                    run_dir / "target" / "stages" / sample_id / _safe_path(system_name)
                ),
                resume=resume,
            )
            append_jsonl(paths["si_cards"], si_card)
            append_jsonl(paths["results"], result)
            results.append(result)
            si_cards[key] = si_card
            completed.add(key)
            failures = _remove_failure(failures, "si", sample_id, system_name)
        except Exception as exc:
            failures.append({
                "stage": "si", "sample_id": sample_id, "system_name": system_name,
                "error": str(exc),
            })

    failures = _deduplicate_failures(failures)
    results.sort(key=lambda r: (str(r.get("sample_id")), str(r.get("system_name"))))
    write_jsonl(paths["results"], results)
    write_jsonl(paths["failures"], failures)
    metrics = compute_v07_metrics(results, failures)
    metrics["paths"] = {k: str(v) for k, v in paths.items()}
    write_json(paths["metrics"], metrics)
    return metrics


def compute_v07_metrics(
    results: list[dict[str, Any]], failures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[str(result.get("system_name"))].append(result)
    systems: dict[str, Any] = {}
    for system_name, rows in sorted(grouped.items()):
        final_rows = [
            r for r in rows
            if r.get("score_status") == "final" and _is_number(r.get("final_score"))
        ]
        provisional_rows = [
            r for r in rows
            if r.get("score_status") != "final" and _is_number(r.get("final_score"))
        ]
        systems[system_name] = {
            "samples": len(rows),
            "average_score": _mean([float(r["final_score"]) for r in final_rows]),
            "provisional_average_score": _mean([
                float(r["final_score"]) for r in provisional_rows
            ]),
            "final_results": len(final_rows),
            "provisional_results": len(rows) - len(final_rows),
            "dimension_scores": {
                dim: _mean([
                    float(r["dimension_scores"][dim])
                    for r in final_rows
                    if _is_number(r.get("dimension_scores", {}).get(dim))
                ])
                for dim in DIMENSION_WEIGHTS_V07
            },
        }
    final_rows = [
        r for r in results
        if r.get("score_status") == "final" and _is_number(r.get("final_score"))
    ]
    return {
        "protocol_version": PROTOCOL_VERSION_V07,
        "implementation_version": IMPLEMENTATION_VERSION_V07,
        "num_results": len(results),
        "num_failures": len(failures or []),
        "num_final_results": len(final_rows),
        "num_provisional_results": len(results) - len(final_rows),
        "average_score": _mean([float(r["final_score"]) for r in final_rows]),
        "systems": systems,
    }


def check_v07_input_files(samples_path: str, outputs_path: str) -> dict[str, Any]:
    """Validate and summarize v0.7 inputs without creating a client or calling an LLM."""
    raw_samples = read_jsonl(samples_path)
    raw_outputs = read_jsonl(outputs_path)
    samples = [_normalize_sample(row) for row in raw_samples]
    outputs = [_normalize_output(row) for row in raw_outputs]
    _validate_inputs(samples, outputs)
    outputs_by_sample: dict[str, int] = defaultdict(int)
    systems: set[str] = set()
    for row in outputs:
        outputs_by_sample[row["sample_id"]] += 1
        systems.add(row["system_name"])
    return {
        "valid": True,
        "protocol_version": PROTOCOL_VERSION_V07,
        "num_samples": len(samples),
        "num_outputs": len(outputs),
        "systems": sorted(systems),
        "outputs_by_sample": dict(sorted(outputs_by_sample.items())),
    }


# ── input normalization ─────────────────────────────────────────────

def _normalize_sample(row: dict[str, Any]) -> dict[str, Any]:
    reference = row.get("reference_translation", row.get("offline_translation"))
    return {
        "sample_id": str(row.get("sample_id") or row.get("vid") or "").strip(),
        "source_text": str(row.get("source_text") or row.get("transcript") or ""),
        "reference_translation": str(reference or ""),
        "reference_type": str(row.get("reference_type") or "machine_offline"),
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


# ── validation ──────────────────────────────────────────────────────

def _validate_inputs(
    samples: list[dict[str, Any]], outputs: list[dict[str, Any]],
) -> None:
    ids = [row["sample_id"] for row in samples]
    if not samples or any(not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("v0.7 samples need unique non-empty sample_id values")
    for row in samples:
        if not row["source_text"].strip() or not row["reference_translation"].strip():
            raise ValueError(
                "v0.7 requires non-empty source_text and reference_translation"
            )
    valid_ids = set(ids)
    keys = []
    for row in outputs:
        key = (row["sample_id"], row["system_name"])
        if (
            row["sample_id"] not in valid_ids
            or not row["system_name"]
            or not row["si_translation"].strip()
        ):
            raise ValueError("invalid v0.7 system output")
        keys.append(key)
    if not outputs or len(keys) != len(set(keys)):
        raise ValueError("v0.7 outputs need unique (sample_id, system_name) pairs")


def _select_rows(
    samples: list[dict[str, Any]], outputs: list[dict[str, Any]],
    sample_ids: list[str] | None, system_names: list[str] | None,
    limit_samples: int | None, limit_outputs: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sample_filter = set(sample_ids) if sample_ids else None
    system_filter = set(system_names) if system_names else None
    selected_samples = [
        r for r in samples if sample_filter is None or r["sample_id"] in sample_filter
    ]
    if limit_samples is not None:
        selected_samples = selected_samples[:limit_samples]
    selected_ids = {r["sample_id"] for r in selected_samples}
    selected_outputs = [
        r for r in outputs
        if r["sample_id"] in selected_ids
        and (system_filter is None or r["system_name"] in system_filter)
    ]
    if limit_outputs is not None:
        selected_outputs = selected_outputs[:limit_outputs]
    required = {r["sample_id"] for r in selected_outputs}
    selected_samples = [r for r in selected_samples if r["sample_id"] in required]
    if not selected_samples or not selected_outputs:
        raise ValueError("v0.7 selection produced no source/output pairs")
    return selected_samples, selected_outputs


# ── manifest & resume ───────────────────────────────────────────────

def _manifest(
    samples_path: str, outputs_path: str,
    samples: list[dict[str, Any]], outputs: list[dict[str, Any]],
    client: LLMClient,
) -> dict[str, Any]:
    hashes = prompt_manifest()
    return {
        "protocol_version": PROTOCOL_VERSION_V07,
        "implementation_version": IMPLEMENTATION_VERSION_V07,
        "implementation_hash": _implementation_hash(),
        "samples_sha256": _file_hash(samples_path),
        "outputs_sha256": _file_hash(outputs_path),
        "selected_sample_ids": [r["sample_id"] for r in samples],
        "selected_output_keys": [
            [r["sample_id"], r["system_name"]] for r in outputs
        ],
        "prompt_hashes": {n: hashes[n] for n in V07_PROMPTS},
        "provider": client.provider_name,
        "model": client.model_name,
        "provider_runtime": _provider_runtime(client),
        "dimension_weights": DIMENSION_WEIGHTS_V07,
    }


def _assert_resume_compatible(
    existing: dict[str, Any], current: dict[str, Any],
) -> None:
    changed = [k for k, v in current.items() if existing.get(k) != v]
    if changed:
        raise ValueError(
            "Cannot resume v0.7 run — configuration changed: " + ", ".join(changed)
        )


def _validate_resume_joint_cards(
    samples: list[dict[str, Any]],
    joint_cards: dict[str, dict[str, Any]],
) -> None:
    sample_by_id = {r["sample_id"]: r for r in samples}
    extra = set(joint_cards) - set(sample_by_id)
    if extra:
        raise ValueError(f"v0.7 resume joint cards contain unexpected IDs: {extra}")
    for sample_id, card in joint_cards.items():
        sample = sample_by_id[sample_id]
        if card.get("source_text") != sample["source_text"]:
            raise ValueError(f"v0.7 joint card source_text mismatch for {sample_id}")
        if card.get("reference_translation") != sample["reference_translation"]:
            raise ValueError(
                f"v0.7 joint card reference_translation mismatch for {sample_id}"
            )
        expected_hash = str(card.get("metadata", {}).get("joint_card_hash") or "")
        if not expected_hash or expected_hash != artifact_hash(card):
            raise ValueError(f"v0.7 joint card hash mismatch for {sample_id}")


# ── helpers ─────────────────────────────────────────────────────────

def _implementation_hash() -> str:
    root = Path(__file__).resolve().parent
    payload = b"".join(
        (root / name).read_bytes()
        for name in (
            "config.py", "llm_provider.py", "v07_agents.py",
            "v07_validation.py", "v07_pipeline.py", "prompt_loader.py",
        )
    )
    return hashlib.sha256(payload).hexdigest()


def _file_hash(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _safe_path(value: str) -> str:
    safe = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in value
    )
    return safe or "anonymous_system"


def _provider_runtime(client: LLMClient) -> dict[str, Any]:
    config = getattr(client, "config", None)
    if config is None:
        return {}
    return {
        "timeout_seconds": config.timeout_seconds,
        "max_retries": config.max_retries,
        "max_output_tokens": config.max_output_tokens,
    }


def _remove_failure(
    rows: list[dict[str, Any]], stage: str, sample_id: str,
    system_name: str | None,
) -> list[dict[str, Any]]:
    return [
        r for r in rows
        if not (
            r.get("stage") == stage
            and r.get("sample_id") == sample_id
            and r.get("system_name") == system_name
        )
    ]


def _deduplicate_failures(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("stage") or ""),
            str(row.get("sample_id") or ""),
            str(row.get("system_name") or ""),
        )
        output[key] = row
    return list(output.values())
