from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

from .card_builder import build_source_card
from .config import get_provider_config, get_review_provider_name
from .evaluator import evaluate_translation
from .io_utils import append_jsonl, read_json, read_jsonl, write_json, write_jsonl
from .llm_provider import HTTPJSONClient, LLMClient
from .prompt_loader import prompt_manifest
from .report import export_html_report
from .scoring import DIMENSION_WEIGHTS, score_evaluation


PIPELINE_VERSION = "0.4.1"


def run_pipeline(
    samples_path: str,
    outputs_path: str,
    output_dir: str = "results",
    run_name: str = "evaluation_run",
    provider_name: str = "deepseek",
    review_provider_name: str | None = None,
    resume: bool = False,
    primary_client: LLMClient | None = None,
    review_client: LLMClient | None = None,
) -> dict[str, Any]:
    samples = read_jsonl(samples_path)
    outputs = read_jsonl(outputs_path)
    _validate_inputs(samples, outputs)

    if primary_client is None:
        primary_client = HTTPJSONClient(get_provider_config(provider_name))
    if review_client is None:
        review_name = review_provider_name or get_review_provider_name(primary_client.provider_name)
        review_client = HTTPJSONClient(get_provider_config(review_name))

    run_dir = Path(output_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "cards": run_dir / "source_cards.jsonl",
        "partial": run_dir / "partial_results.jsonl",
        "results": run_dir / "results.jsonl",
        "failures": run_dir / "failures.jsonl",
        "metrics": run_dir / "metrics.json",
        "manifest": run_dir / "run_manifest.json",
        "report": run_dir / "report.html",
    }
    manifest = _manifest(samples_path, outputs_path, primary_client, review_client)
    if resume and paths["manifest"].exists():
        _assert_resume_compatible(read_json(paths["manifest"]), manifest)
    elif not resume:
        for key in ("cards", "partial", "failures"):
            write_jsonl(paths[key], [])
    write_json(paths["manifest"], manifest)

    cards = {
        str(item["sample_id"]): item
        for item in (read_jsonl(paths["cards"]) if resume and paths["cards"].exists() else [])
    }
    failures = read_jsonl(paths["failures"]) if resume and paths["failures"].exists() else []
    for sample in samples:
        sample_id = str(sample["sample_id"])
        if sample_id in cards:
            continue
        try:
            card = build_source_card(sample, primary_client)
            cards[sample_id] = card
            append_jsonl(paths["cards"], card)
        except Exception as exc:
            failure = {"stage": "source_card", "sample_id": sample_id, "error": str(exc)}
            failures.append(failure)
            append_jsonl(paths["failures"], failure)

    results = read_jsonl(paths["partial"]) if resume and paths["partial"].exists() else []
    completed = {(str(item["sample_id"]), str(item["system_name"])) for item in results}
    for output in outputs:
        sample_id = str(output["sample_id"])
        system_name = str(output.get("system_name") or "system")
        key = (sample_id, system_name)
        if key in completed:
            continue
        if sample_id not in cards:
            failure = {"stage": "evaluation", "sample_id": sample_id, "system_name": system_name, "error": "No validated source card"}
            failures.append(failure)
            append_jsonl(paths["failures"], failure)
            continue
        try:
            evaluated = evaluate_translation(
                cards[sample_id],
                system_name,
                str(output.get("si_translation") or ""),
                primary_client,
                review_client,
            )
            result = score_evaluation(evaluated)
            for field in ("expected_label", "expected_errors", "label_notes"):
                if field in output:
                    result[field] = output[field]
            results.append(result)
            completed.add(key)
            append_jsonl(paths["partial"], result)
        except Exception as exc:
            failure = {"stage": "evaluation", "sample_id": sample_id, "system_name": system_name, "error": str(exc)}
            failures.append(failure)
            append_jsonl(paths["failures"], failure)

    results.sort(key=lambda item: (str(item["sample_id"]), str(item["system_name"])))
    write_jsonl(paths["results"], results)
    metrics = compute_metrics(results, failures)
    metrics["paths"] = {key: str(path) for key, path in paths.items()}
    write_json(paths["metrics"], metrics)
    export_html_report(results, metrics, paths["report"])
    return metrics


def compute_metrics(results: list[dict[str, Any]], failures: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[str(result["system_name"])].append(result)
    systems = {}
    for system_name, rows in sorted(grouped.items()):
        dimensions = {}
        for dimension in DIMENSION_WEIGHTS:
            values = [row.get("dimension_scores", {}).get(dimension, {}).get("score") for row in rows]
            numeric = [float(value) for value in values if isinstance(value, (int, float))]
            dimensions[dimension] = _mean(numeric) if numeric else None
        systems[system_name] = {
            "samples": len(rows),
            "average_score": _mean([float(row["final_score"]) for row in rows]),
            "dimension_average_points": dimensions,
            "confirmed_errors": sum(len(row.get("attributed_errors", [])) for row in rows),
            "pending_reviews": sum(len(row.get("review_queue", [])) for row in rows),
        }
    return {
        "version": PIPELINE_VERSION,
        "num_results": len(results),
        "num_failures": len(failures or []),
        "average_score": _mean([float(row["final_score"]) for row in results]),
        "systems": systems,
    }


def _manifest(samples_path: str, outputs_path: str, primary: LLMClient, review: LLMClient) -> dict[str, Any]:
    return {
        "pipeline_version": PIPELINE_VERSION,
        "samples_sha256": _file_hash(samples_path),
        "outputs_sha256": _file_hash(outputs_path),
        "prompt_hashes": prompt_manifest(),
        "dimension_weights": DIMENSION_WEIGHTS,
        "primary_provider": primary.provider_name,
        "primary_model": primary.model_name,
        "review_provider": review.provider_name,
        "review_model": review.model_name,
    }


def _assert_resume_compatible(existing: dict[str, Any], current: dict[str, Any]) -> None:
    keys = ("pipeline_version", "samples_sha256", "outputs_sha256", "prompt_hashes", "dimension_weights", "primary_provider", "primary_model", "review_provider", "review_model")
    changed = [key for key in keys if existing.get(key) != current.get(key)]
    if changed:
        raise ValueError("Cannot resume because run inputs or configuration changed: " + ", ".join(changed))


def _validate_inputs(samples: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> None:
    sample_ids = [str(item.get("sample_id") or "") for item in samples]
    if any(not item for item in sample_ids) or len(sample_ids) != len(set(sample_ids)):
        raise ValueError("samples must contain unique non-empty sample_id values")
    valid_ids = set(sample_ids)
    output_keys = []
    for item in outputs:
        sample_id = str(item.get("sample_id") or "")
        system_name = str(item.get("system_name") or "")
        if sample_id not in valid_ids:
            raise ValueError(f"output references unknown sample_id={sample_id}")
        if not system_name or not str(item.get("si_translation") or "").strip():
            raise ValueError("every output needs system_name and si_translation")
        output_keys.append((sample_id, system_name))
    if len(output_keys) != len(set(output_keys)):
        raise ValueError("outputs must contain unique (sample_id, system_name) pairs")


def _file_hash(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None
