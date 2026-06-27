from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .agent_aggregator import DIMENSION_WEIGHTS, aggregate_agent_result
from .agent_card_builder import build_agent_card
from .agent_evaluator import evaluate_with_agents
from .agent_report import export_agent_html
from .config import get_provider_config, get_review_provider_name
from .io_utils import append_jsonl, read_jsonl, write_jsonl
from .llm_provider import HTTPJSONClient, LLMClient


def run_agent_pipeline(
    samples_path: str,
    outputs_path: str,
    output_dir: str = "results",
    run_name: str = "agent_run",
    provider_name: str = "deepseek",
    review_provider_name: str | None = None,
    skip_card_build: bool = False,
    resume: bool = False,
    primary_client: LLMClient | None = None,
    review_client: LLMClient | None = None,
) -> dict[str, Any]:
    primary = primary_client or HTTPJSONClient(get_provider_config(provider_name))
    if review_client is not None:
        reviewer = review_client
    else:
        review_name = review_provider_name or get_review_provider_name(provider_name)
        reviewer = HTTPJSONClient(get_provider_config(review_name))

    run_root = Path(output_dir) / run_name
    card_path = run_root / "cards" / "cards.jsonl"
    eval_dir = run_root / "evaluation_result" / "evisi_agent"
    result_path = eval_dir / "results.jsonl"
    partial_result_path = eval_dir / "partial_results.jsonl"
    metrics_path = eval_dir / "metrics.json"
    bad_cases_path = eval_dir / "bad_cases.jsonl"
    review_queue_path = eval_dir / "review_queue.jsonl"
    failures_path = eval_dir / "failures.jsonl"
    report_path = eval_dir / "report.html"
    manifest_path = run_root / "run_manifest.json"
    eval_dir.mkdir(parents=True, exist_ok=True)

    sample_rows = read_jsonl(samples_path)
    _assert_unique(sample_rows, "sample_id", "samples")
    failures: list[dict[str, Any]] = []
    if skip_card_build or (resume and card_path.exists()):
        if not card_path.exists():
            raise FileNotFoundError(f"--skip-card-build requested but {card_path} does not exist")
        card_rows = read_jsonl(card_path)
    else:
        card_rows = []
        for sample in sample_rows:
            try:
                card_rows.append(build_agent_card(sample, primary))
            except Exception as exc:
                failures.append(
                    {"stage": "build_card", "sample_id": sample.get("sample_id"), "error": str(exc)}
                )
        write_jsonl(card_path, card_rows)
    cards = {row["sample_id"]: row for row in card_rows}

    results = read_jsonl(partial_result_path) if resume and partial_result_path.exists() else []
    failures = read_jsonl(failures_path) if resume and failures_path.exists() else failures
    if not resume:
        write_jsonl(partial_result_path, [])
        write_jsonl(failures_path, failures)
    completed = {(row.get("sample_id"), row.get("system_name")) for row in results}
    for row in read_jsonl(outputs_path):
        sample_id = row.get("sample_id")
        result_key = (sample_id, str(row.get("system_name") or "system"))
        if result_key in completed:
            continue
        if sample_id not in cards:
            failure = {"stage": "evaluate", "sample_id": sample_id, "system_name": row.get("system_name"), "error": "No Evaluation Card"}
            failures.append(failure)
            append_jsonl(failures_path, failure)
            continue
        try:
            agent_result = evaluate_with_agents(
                cards[sample_id],
                str(row.get("system_name") or "system"),
                str(row.get("si_translation") or ""),
                primary,
                reviewer,
            )
            result = aggregate_agent_result(agent_result)
            results.append(result)
            append_jsonl(partial_result_path, result)
            completed.add(result_key)
        except Exception as exc:
            failure = {"stage": "evaluate", "sample_id": sample_id, "system_name": row.get("system_name"), "error": str(exc)}
            failures.append(failure)
            append_jsonl(failures_path, failure)

    write_jsonl(result_path, results)
    write_jsonl(bad_cases_path, [row for row in results if row.get("attributed_errors")])
    write_jsonl(
        review_queue_path,
        [
            {"sample_id": row["sample_id"], "system_name": row["system_name"], **item}
            for row in results
            for item in row.get("review_queue", [])
        ],
    )
    write_jsonl(failures_path, failures)
    export_agent_html(results, report_path)

    metrics = compute_agent_metrics(results, failures)
    metrics["paths"] = {
        "cards": str(card_path),
        "results": str(result_path),
        "partial_results": str(partial_result_path),
        "metrics": str(metrics_path),
        "bad_cases": str(bad_cases_path),
        "review_queue": str(review_queue_path),
        "failures": str(failures_path),
        "report": str(report_path),
        "manifest": str(manifest_path),
    }
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "protocol": "evisi_llm_agent_v1.0",
        "primary_provider": primary.provider_name,
        "primary_model": primary.model_name,
        "review_provider": reviewer.provider_name,
        "review_model": reviewer.model_name,
        "dimension_weights": DIMENSION_WEIGHTS,
        "samples_sha256": _file_hash(samples_path),
        "outputs_sha256": _file_hash(outputs_path),
        "sample_count": len(sample_rows),
        "card_count": len(card_rows),
        "result_count": len(results),
        "failure_count": len(failures),
        "resume_enabled": resume,
        "system_asr_used": False,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return metrics


def compute_agent_metrics(results: list[dict[str, Any]], failures: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[str(result.get("system_name", "system"))].append(result)
    by_system = {}
    for system, rows in sorted(grouped.items()):
        by_dimension = {}
        for dimension in DIMENSION_WEIGHTS:
            values = [row.get("dimension_scores", {}).get(dimension, {}).get("score") for row in rows]
            numeric = [float(value) for value in values if isinstance(value, (int, float))]
            by_dimension[dimension] = _mean(numeric) if numeric else None
        by_system[system] = {
            "count": len(rows),
            "average_score": _mean([float(row.get("final_score", 0)) for row in rows]),
            "dimension_average_points": by_dimension,
            "confirmed_error_count": sum(len(row.get("attributed_errors", [])) for row in rows),
            "review_required_count": sum(len(row.get("review_queue", [])) for row in rows),
            "cap_count": sum(bool(row.get("cap_triggered")) for row in rows),
        }
    return {
        "version": "1.0.0",
        "protocol": "evisi_llm_agent_v1.0",
        "num_results": len(results),
        "average_score": _mean([float(row.get("final_score", 0)) for row in results]),
        "confirmed_error_count": sum(len(row.get("attributed_errors", [])) for row in results),
        "review_required_count": sum(len(row.get("review_queue", [])) for row in results),
        "failure_count": len(failures or []),
        "by_system": by_system,
    }


def _assert_unique(rows: list[dict[str, Any]], key: str, label: str) -> None:
    values = [row.get(key) for row in rows]
    duplicates = sorted({value for value in values if value is not None and values.count(value) > 1})
    if duplicates:
        raise ValueError(f"Duplicate {key} values in {label}: {duplicates[:5]}")


def _file_hash(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0
