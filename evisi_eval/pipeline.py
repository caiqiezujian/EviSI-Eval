"""File orchestration for the frozen-source v0.5 evaluation agents."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .agents import EvaluationAgentLoop, SourceCardAgent
from .config import get_provider_config, get_review_provider_name
from .io_utils import append_jsonl, read_json, read_jsonl, write_json, write_jsonl
from .llm_provider import HTTPJSONClient, LLMClient
from .prompt_loader import prompt_manifest
from .report import export_html_report
from .validation import (
    DIMENSIONS,
    DIMENSION_WEIGHTS,
    PROTOCOL_VERSION,
    SEVERITY_DEDUCTIONS,
    VERDICT_VALUES,
    validate_alignment_artifact,
    validate_delivery_artifact,
    validate_source_card_artifact,
    validate_target_evidence_artifact,
)


IMPLEMENTATION_VERSION = "0.5.0"
ARTIFACT_FILES = {
    "source_cards": "source/source_cards.jsonl",
    "target_eval_cards": "target/target_eval_cards.jsonl",
    "primary_judgements": "score/score_01_primary_judgements.jsonl",
    "review_judgements": "score/score_02_review_judgements.jsonl",
    "adjudications": "score/score_03_adjudications.jsonl",
    "score_06_final_results": "score/score_06_final_results.jsonl",
}


def run_pipeline(
    samples_path: str,
    outputs_path: str,
    output_dir: str = "results",
    run_name: str = "evaluation_run",
    provider_name: str = "deepseek",
    review_provider_name: str | None = None,
    resume: bool = False,
    sample_ids: list[str] | None = None,
    system_names: list[str] | None = None,
    limit_samples: int | None = None,
    limit_outputs: int | None = None,
    primary_client: LLMClient | None = None,
    review_client: LLMClient | None = None,
    source_card_cache_path: str | None = None,
    target_card_cache_path: str | None = None,
) -> dict[str, Any]:
    all_samples = [_normalize_sample(row) for row in read_jsonl(samples_path)]
    all_outputs = [_normalize_output(row) for row in read_jsonl(outputs_path)]
    _validate_inputs(all_samples, all_outputs)
    samples, outputs = _select_rows(
        all_samples, all_outputs, sample_ids, system_names, limit_samples, limit_outputs
    )

    injected_primary = primary_client is not None
    if primary_client is None:
        primary_client = HTTPJSONClient(get_provider_config(provider_name))
    if review_client is None:
        if injected_primary and review_provider_name is None:
            review_client = primary_client
        else:
            review_name = review_provider_name or get_review_provider_name(primary_client.provider_name)
            review_client = HTTPJSONClient(get_provider_config(review_name))

    run_dir = Path(output_dir) / run_name
    paths = {key: run_dir / value for key, value in ARTIFACT_FILES.items()}
    paths.update(
        {
            "source_input": run_dir / "source/source_00_input.jsonl",
            "target_input": run_dir / "target/target_00_input.jsonl",
            "failures": run_dir / "failures.jsonl",
            "metrics": run_dir / "metrics.json",
            "manifest": run_dir / "run_manifest.json",
            "report": run_dir / "report.html",
            "agent_trace": run_dir / "agent_trace.jsonl",
        }
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(
        samples_path, outputs_path, samples, outputs, primary_client, review_client,
        source_card_cache_path, target_card_cache_path,
    )
    if resume and paths["manifest"].exists():
        _assert_resume_compatible(read_json(paths["manifest"]), manifest)
    elif not resume:
        for path in paths.values():
            if path.suffix == ".jsonl":
                write_jsonl(path, [])
    write_json(paths["manifest"], manifest)
    write_jsonl(paths["source_input"], samples)
    write_jsonl(paths["target_input"], outputs)

    failures = read_jsonl(paths["failures"]) if resume else []
    cards = {
        str(row["sample_id"]): row
        for row in (read_jsonl(paths["source_cards"]) if resume else [])
    }
    sample_by_id = {str(row["sample_id"]): row for row in samples}
    if source_card_cache_path:
        for cached_card in read_jsonl(source_card_cache_path):
            sample_id = str(cached_card.get("sample_id") or "")
            sample = sample_by_id.get(sample_id)
            if sample is None or sample_id in cards:
                continue
            _validate_cached_source_card(cached_card, sample)
            cards[sample_id] = cached_card
            append_jsonl(paths["source_cards"], cached_card)
    source_agent = SourceCardAgent(primary_client)
    for sample in samples:
        sample_id = str(sample["sample_id"])
        if sample_id in cards:
            continue
        try:
            card, _ = source_agent.build(sample)
            cards[sample_id] = card
            append_jsonl(paths["source_cards"], card)
        except Exception as exc:
            failure = {"stage": "source_card", "sample_id": sample_id, "error": str(exc)}
            failures.append(failure)
            append_jsonl(paths["failures"], failure)

    results = read_jsonl(paths["score_06_final_results"]) if resume else []
    completed = {(str(row["sample_id"]), str(row["system_name"])) for row in results}
    evaluation_loop = EvaluationAgentLoop(primary_client, review_client)
    target_card_cache = _load_target_card_cache(target_card_cache_path)

    def target_sink(stage: str, artifact: dict[str, Any]) -> None:
        append_jsonl(paths[stage], artifact)

    def score_sink(stage: str, artifact: dict[str, Any]) -> None:
        append_jsonl(paths[stage], artifact)

    for output in outputs:
        key = (str(output["sample_id"]), str(output["system_name"]))
        if key in completed:
            continue
        source_card = cards.get(key[0])
        if source_card is None:
            failure = {
                "stage": "evaluation",
                "sample_id": key[0],
                "system_name": key[1],
                "error": "No validated frozen source card",
            }
            failures.append(failure)
            append_jsonl(paths["failures"], failure)
            continue
        try:
            cached_target_card = target_card_cache.get(key)
            if cached_target_card is not None:
                _validate_cached_target_card(cached_target_card, source_card, output)
            result, _ = evaluation_loop.run(
                source_card, output, target_sink, score_sink,
                cached_target_card=cached_target_card,
            )
            results.append(result)
            completed.add(key)
            append_jsonl(
                paths["agent_trace"],
                {
                    "sample_id": key[0],
                    "system_name": key[1],
                    "source_card_hash": source_card["metadata"]["source_card_hash"],
                    "agent_trace": result["metadata"]["agent_trace"],
                },
            )
        except Exception as exc:
            failure = {
                "stage": "evaluation",
                "sample_id": key[0],
                "system_name": key[1],
                "source_card_hash": source_card["metadata"]["source_card_hash"],
                "error": str(exc),
            }
            failures.append(failure)
            append_jsonl(paths["failures"], failure)

    results.sort(key=lambda row: (str(row["sample_id"]), str(row["system_name"])))
    write_jsonl(paths["score_06_final_results"], results)
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
        final_rows = [
            row for row in rows
            if row.get("score_status") == "final" and _is_number(row.get("final_score"))
        ]
        provisional_rows = [
            row for row in rows
            if row.get("score_status") != "final" and _is_number(row.get("final_score"))
        ]
        scored_rows = final_rows + provisional_rows
        systems[system_name] = {
            "samples": len(rows),
            "average_score": _mean([float(row["final_score"]) for row in final_rows]),
            "provisional_average_score": _mean(
                [float(row["final_score"]) for row in provisional_rows]
            ),
            "diagnostic_average_score_including_provisional": _mean(
                [float(row["final_score"]) for row in scored_rows]
            ),
            "final_results": len(final_rows),
            "provisional_results": sum(row.get("score_status") != "final" for row in rows),
            "unscored_results": sum(not _is_number(row.get("final_score")) for row in rows),
            "dimension_scores": {
                dimension: _mean(
                    [
                        float(row["dimension_scores"][dimension])
                        for row in final_rows
                        if _is_number(row.get("dimension_scores", {}).get(dimension))
                        and _dimension_is_applicable(row, dimension)
                    ]
                )
                for dimension in DIMENSIONS
            },
        }
    final_results = [
        row for row in results
        if row.get("score_status") == "final" and _is_number(row.get("final_score"))
    ]
    provisional_results = [
        row for row in results
        if row.get("score_status") != "final" and _is_number(row.get("final_score"))
    ]
    return {
        "protocol_version": PROTOCOL_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "num_results": len(results),
        "num_failures": len(failures or []),
        "average_score": _mean([float(row["final_score"]) for row in final_results]),
        "provisional_average_score": _mean(
            [float(row["final_score"]) for row in provisional_results]
        ),
        "diagnostic_average_score_including_provisional": _mean(
            [float(row["final_score"]) for row in final_results + provisional_results]
        ),
        "num_final_results": len(final_results),
        "num_provisional_results": sum(
            row.get("score_status") != "final" for row in results
        ),
        "num_unscored_results": sum(
            not _is_number(row.get("final_score")) for row in results
        ),
        "systems": systems,
    }


def _normalize_sample(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": str(row.get("sample_id") or row.get("vid") or "").strip(),
        "source_text": str(row.get("source_text") or row.get("transcript") or ""),
        "reference_translation": row.get("reference_translation", row.get("offline_translation")),
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


def _validate_inputs(samples: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> None:
    sample_ids = [row["sample_id"] for row in samples]
    if any(not value for value in sample_ids) or len(sample_ids) != len(set(sample_ids)):
        raise ValueError("samples must have unique non-empty sample_id values")
    if any(not row["source_text"].strip() for row in samples):
        raise ValueError("every sample needs non-empty source_text")
    valid_ids = set(sample_ids)
    output_keys = []
    for row in outputs:
        if row["sample_id"] not in valid_ids or not row["system_name"] or not row["si_translation"].strip():
            raise ValueError("every output must reference a sample and contain system_name/si_translation")
        output_keys.append((row["sample_id"], row["system_name"]))
    if len(output_keys) != len(set(output_keys)):
        raise ValueError("outputs must have unique (sample_id, system_name) pairs")


def _select_rows(
    samples: list[dict[str, Any]], outputs: list[dict[str, Any]], sample_ids: list[str] | None,
    system_names: list[str] | None, limit_samples: int | None, limit_outputs: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sample_filter = set(sample_ids) if sample_ids is not None else None
    system_filter = set(system_names) if system_names is not None else None
    selected_samples = [row for row in samples if sample_filter is None or row["sample_id"] in sample_filter]
    if limit_samples is not None:
        selected_samples = selected_samples[:limit_samples]
    selected_ids = {row["sample_id"] for row in selected_samples}
    selected_outputs = [
        row for row in outputs
        if row["sample_id"] in selected_ids and (system_filter is None or row["system_name"] in system_filter)
    ]
    if limit_outputs is not None:
        selected_outputs = selected_outputs[:limit_outputs]
    required_ids = {row["sample_id"] for row in selected_outputs}
    selected_samples = [row for row in selected_samples if row["sample_id"] in required_ids]
    if not selected_samples or not selected_outputs:
        raise ValueError("selection produced no sample/output pairs")
    return selected_samples, selected_outputs


def _manifest(
    samples_path: str, outputs_path: str, samples: list[dict[str, Any]], outputs: list[dict[str, Any]],
    primary: LLMClient, reviewer: LLMClient, source_card_cache_path: str | None,
    target_card_cache_path: str | None,
) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "implementation_hash": _implementation_hash(),
        "samples_sha256": _file_hash(samples_path),
        "outputs_sha256": _file_hash(outputs_path),
        "selected_sample_ids": [row["sample_id"] for row in samples],
        "selected_output_keys": [[row["sample_id"], row["system_name"]] for row in outputs],
        "prompt_hashes": prompt_manifest(),
        "scoring_policy": {
            "dimension_weights": DIMENSION_WEIGHTS,
            "verdict_values": VERDICT_VALUES,
            "severity_deductions": SEVERITY_DEDUCTIONS,
            "not_applicable_dimensions": "zero_weight_then_renormalize",
        },
        "primary_provider": primary.provider_name,
        "primary_model": primary.model_name,
        "review_provider": reviewer.provider_name,
        "review_model": reviewer.model_name,
        "source_card_cache_sha256": (
            _file_hash(source_card_cache_path) if source_card_cache_path else None
        ),
        "target_card_cache_sha256": (
            _file_hash(target_card_cache_path) if target_card_cache_path else None
        ),
    }


def _assert_resume_compatible(existing: dict[str, Any], current: dict[str, Any]) -> None:
    changed = [key for key, value in current.items() if existing.get(key) != value]
    if changed:
        raise ValueError("Cannot resume because run configuration changed: " + ", ".join(changed))


def _implementation_hash() -> str:
    root = Path(__file__).resolve().parent
    payload = b"".join((root / name).read_bytes() for name in ("agents.py", "validation.py", "pipeline.py"))
    return hashlib.sha256(payload).hexdigest()


def _file_hash(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _validate_cached_source_card(card: dict[str, Any], sample: dict[str, Any]) -> None:
    if card.get("source_text") != sample.get("source_text"):
        raise ValueError(f"cached source card text mismatch for sample_id={sample['sample_id']}")
    issues = validate_source_card_artifact(card, str(sample["source_text"]))
    if issues:
        raise ValueError(
            f"cached source card failed validation for sample_id={sample['sample_id']}: "
            + "; ".join(issues)
        )
    expected_hash = str(card.get("metadata", {}).get("source_card_hash") or "")
    payload = {key: value for key, value in card.items() if key != "metadata"}
    actual_hash = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if not expected_hash or expected_hash != actual_hash:
        raise ValueError(f"cached source card hash mismatch for sample_id={sample['sample_id']}")


def _load_target_card_cache(path: str | None) -> dict[tuple[str, str], dict[str, Any]]:
    if not path:
        return {}
    return {
        (str(row.get("sample_id") or ""), str(row.get("system_name") or "")): row
        for row in read_jsonl(path)
    }


def _validate_cached_target_card(
    card: dict[str, Any], source_card: dict[str, Any], output: dict[str, Any]
) -> None:
    sample_id = str(output["sample_id"])
    system_name = str(output["system_name"])
    translation = str(output["si_translation"])
    if card.get("sample_id") != sample_id or card.get("system_name") != system_name:
        raise ValueError(f"cached target card identity mismatch for {sample_id}/{system_name}")
    if card.get("si_translation") != translation:
        raise ValueError(f"cached target card translation mismatch for {sample_id}/{system_name}")
    issues = validate_alignment_artifact(
        {"eval_units": card.get("eval_units")}, source_card["source_units"], translation
    )
    target_units = [
        {"eval_unit_id": row.get("eval_unit_id"), "target_unit": row.get("target_unit", "")}
        for row in card.get("eval_units", []) if isinstance(row, dict)
    ]
    issues.extend(validate_target_evidence_artifact(card, target_units))
    issues.extend(validate_delivery_artifact(
        card, translation, "fluency_issues", "fluency_assessment", "F"
    ))
    issues.extend(validate_delivery_artifact(
        card, translation, "si_expression_issues", "si_expression_assessment", "X"
    ))
    if issues:
        raise ValueError(
            f"cached target card failed validation for {sample_id}/{system_name}: "
            + "; ".join(issues)
        )


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _dimension_is_applicable(row: dict[str, Any], dimension: str) -> bool:
    if dimension in {"fluency", "si_expression"}:
        return True
    return bool(
        row.get("score_diagnostics", {}).get(dimension, {}).get("applicable", True)
    )
