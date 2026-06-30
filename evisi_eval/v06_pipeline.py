"""Orchestration for the v0.6 source-conditioned projection protocol."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

from .config import get_provider_config
from .io_utils import append_jsonl, read_json, read_jsonl, write_json, write_jsonl
from .llm_provider import HTTPJSONClient, LLMClient
from .prompt_loader import prompt_manifest
from .v06_agents import (
    V06EvaluationLoop,
    V06ProjectionBuilder,
    V06SourceCardBuilder,
    artifact_hash,
    build_evaluation_context_v06,
    validate_evaluation_context_v06,
    validate_projection_card_v06,
    validate_source_card_v06,
)
from .v06_validation import DIMENSION_WEIGHTS_V06, PROTOCOL_VERSION_V06
from .v06_validation import calculate_v06_scores, validate_requirement_inheritance


IMPLEMENTATION_VERSION_V06 = "0.6.1"
V06_PROMPTS = tuple(name for name in prompt_manifest() if name.startswith("v06_"))


def run_v06_pipeline(
    samples_path: str,
    outputs_path: str,
    output_dir: str = "results",
    run_name: str = "v06_evaluation",
    provider_name: str = "deepseek",
    resume: bool = False,
    sample_ids: list[str] | None = None,
    system_names: list[str] | None = None,
    limit_samples: int | None = None,
    limit_outputs: int | None = None,
    client: LLMClient | None = None,
) -> dict[str, Any]:
    samples = [_normalize_sample(row) for row in read_jsonl(samples_path)]
    outputs = [_normalize_output(row) for row in read_jsonl(outputs_path)]
    _validate_inputs(samples, outputs)
    samples, outputs = _select_rows(
        samples, outputs, sample_ids, system_names, limit_samples, limit_outputs
    )
    if client is None:
        client = HTTPJSONClient(get_provider_config(provider_name))

    run_dir = Path(output_dir) / run_name
    paths = {
        "source_cards": run_dir / "source/source_cards_v06.jsonl",
        "reference_cards": run_dir / "reference/reference_projection_cards.jsonl",
        "evaluation_contexts": run_dir / "context/evaluation_context_cards.jsonl",
        "si_cards": run_dir / "target/si_projection_cards.jsonl",
        "results": run_dir / "score/final_results_v06.jsonl",
        "source_input": run_dir / "source/source_00_input.jsonl",
        "target_input": run_dir / "target/target_00_input.jsonl",
        "failures": run_dir / "failures.jsonl",
        "manifest": run_dir / "run_manifest_v06.json",
        "metrics": run_dir / "metrics_v06.json",
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(samples_path, outputs_path, samples, outputs, client)
    if resume:
        if not paths["manifest"].exists():
            raise ValueError("Cannot resume v0.6 run without run_manifest_v06.json")
        _assert_resume_compatible(read_json(paths["manifest"]), manifest)
    else:
        for path in paths.values():
            if path.suffix == ".jsonl":
                write_jsonl(path, [])
    write_json(paths["manifest"], manifest)
    write_jsonl(paths["source_input"], samples)
    write_jsonl(paths["target_input"], outputs)

    failures = read_jsonl(paths["failures"]) if resume else []
    source_cards = {
        str(row.get("sample_id")): row
        for row in (read_jsonl(paths["source_cards"]) if resume else [])
    }
    reference_cards = {
        str(row.get("sample_id")): row
        for row in (read_jsonl(paths["reference_cards"]) if resume else [])
    }
    evaluation_contexts = {
        str(row.get("sample_id")): row
        for row in (read_jsonl(paths["evaluation_contexts"]) if resume else [])
    }
    si_card_rows = read_jsonl(paths["si_cards"]) if resume else []
    si_cards = {
        (str(row.get("sample_id")), str(row.get("system_name"))): row
        for row in si_card_rows
    }
    results = read_jsonl(paths["results"]) if resume else []
    completed = {(str(row.get("sample_id")), str(row.get("system_name"))) for row in results}
    if resume:
        _validate_resume_cards(
            samples, source_cards, reference_cards, evaluation_contexts
        )
        _validate_resume_si_results(
            outputs, source_cards, reference_cards, evaluation_contexts, si_cards, results
        )

    source_builder = V06SourceCardBuilder(client)
    reference_builder = V06ProjectionBuilder(client, "reference")
    evaluator = V06EvaluationLoop(client)

    for sample in samples:
        sample_id = sample["sample_id"]
        if sample_id not in source_cards:
            try:
                card, _ = source_builder.build(sample)
                source_cards[sample_id] = card
                append_jsonl(paths["source_cards"], card)
                failures = _remove_failure(failures, "source", sample_id, None)
            except Exception as exc:
                failures.append({"stage": "source", "sample_id": sample_id, "error": str(exc)})
                continue
        if sample_id not in reference_cards:
            try:
                card, _ = reference_builder.build(
                    source_cards[sample_id],
                    sample["reference_translation"],
                    reference_type=sample["reference_type"],
                )
                reference_cards[sample_id] = card
                append_jsonl(paths["reference_cards"], card)
                failures = _remove_failure(failures, "reference", sample_id, None)
            except Exception as exc:
                failures.append({"stage": "reference", "sample_id": sample_id, "error": str(exc)})
                continue
        if sample_id not in evaluation_contexts:
            try:
                context = build_evaluation_context_v06(
                    source_cards[sample_id], reference_cards[sample_id]
                )
                evaluation_contexts[sample_id] = context
                append_jsonl(paths["evaluation_contexts"], context)
                failures = _remove_failure(failures, "context", sample_id, None)
            except Exception as exc:
                failures.append({"stage": "context", "sample_id": sample_id, "error": str(exc)})

    sample_by_id = {row["sample_id"]: row for row in samples}
    for output in outputs:
        sample_id = output["sample_id"]
        system_name = output["system_name"]
        key = (sample_id, system_name)
        if key in completed:
            continue
        source_card = source_cards.get(sample_id)
        reference_card = reference_cards.get(sample_id)
        evaluation_context = evaluation_contexts.get(sample_id)
        if source_card is None or reference_card is None or evaluation_context is None:
            failures.append({
                "stage": "si", "sample_id": sample_id, "system_name": system_name,
                "error": "validated source/reference/context artifact is unavailable",
            })
            continue
        try:
            result, si_card = evaluator.run(
                source_card,
                reference_card,
                evaluation_context,
                output,
                sample_by_id[sample_id]["reference_type"],
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
    results.sort(key=lambda row: (str(row.get("sample_id")), str(row.get("system_name"))))
    write_jsonl(paths["results"], results)
    write_jsonl(paths["failures"], failures)
    metrics = compute_v06_metrics(results, failures)
    metrics["paths"] = {key: str(path) for key, path in paths.items()}
    write_json(paths["metrics"], metrics)
    return metrics


def compute_v06_metrics(
    results: list[dict[str, Any]], failures: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[str(result.get("system_name"))].append(result)
    systems: dict[str, Any] = {}
    for system_name, rows in sorted(grouped.items()):
        final_rows = [
            row for row in rows
            if row.get("score_status") == "final" and _is_number(row.get("final_score"))
        ]
        provisional_rows = [
            row for row in rows
            if row.get("score_status") != "final" and _is_number(row.get("final_score"))
        ]
        systems[system_name] = {
            "samples": len(rows),
            "average_score": _mean([float(row["final_score"]) for row in final_rows]),
            "provisional_average_score": _mean(
                [float(row["final_score"]) for row in provisional_rows]
            ),
            "final_results": len(final_rows),
            "provisional_results": len(rows) - len(final_rows),
            "dimension_scores": {
                dimension: _mean([
                    float(row["dimension_scores"][dimension])
                    for row in final_rows
                    if _is_number(row.get("dimension_scores", {}).get(dimension))
                ])
                for dimension in DIMENSION_WEIGHTS_V06
            },
        }
    final_rows = [
        row for row in results
        if row.get("score_status") == "final" and _is_number(row.get("final_score"))
    ]
    provisional_rows = [
        row for row in results
        if row.get("score_status") != "final" and _is_number(row.get("final_score"))
    ]
    return {
        "protocol_version": PROTOCOL_VERSION_V06,
        "implementation_version": IMPLEMENTATION_VERSION_V06,
        "num_results": len(results),
        "num_failures": len(failures or []),
        "num_final_results": len(final_rows),
        "num_provisional_results": len(results) - len(final_rows),
        "average_score": _mean([float(row["final_score"]) for row in final_rows]),
        "provisional_average_score": _mean(
            [float(row["final_score"]) for row in provisional_rows]
        ),
        "systems": systems,
    }


def check_v06_input_files(samples_path: str, outputs_path: str) -> dict[str, Any]:
    """Validate and summarize v0.6 inputs without creating a client or calling an LLM."""
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
        "protocol_version": PROTOCOL_VERSION_V06,
        "num_samples": len(samples),
        "num_outputs": len(outputs),
        "systems": sorted(systems),
        "outputs_by_sample": dict(sorted(outputs_by_sample.items())),
        "normalization": {
            "source_text_aliases": ["source_text", "transcript"],
            "reference_translation_aliases": [
                "reference_translation", "offline_translation",
            ],
            "ignored_fields": ["system_asr"],
        },
    }


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
        "hard_requirements": [
            item for item in row.get("hard_requirements", []) if isinstance(item, dict)
        ] if isinstance(row.get("hard_requirements", []), list) else [],
    }


def _normalize_output(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": str(row.get("sample_id") or row.get("vid") or "").strip(),
        "system_name": str(row.get("system_name") or "").strip(),
        "si_translation": str(row.get("si_translation") or ""),
    }


def _validate_inputs(samples: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> None:
    ids = [row["sample_id"] for row in samples]
    if not samples or any(not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("v0.6 samples need unique non-empty sample_id values")
    for row in samples:
        if not row["source_text"].strip() or not row["reference_translation"].strip():
            raise ValueError("v0.6 requires non-empty source_text and reference_translation")
    valid_ids = set(ids)
    keys = []
    for row in outputs:
        key = (row["sample_id"], row["system_name"])
        if row["sample_id"] not in valid_ids or not row["system_name"] or not row["si_translation"].strip():
            raise ValueError("invalid v0.6 system output")
        keys.append(key)
    if not outputs or len(keys) != len(set(keys)):
        raise ValueError("v0.6 outputs need unique (sample_id, system_name) pairs")


def _select_rows(
    samples: list[dict[str, Any]], outputs: list[dict[str, Any]],
    sample_ids: list[str] | None, system_names: list[str] | None,
    limit_samples: int | None, limit_outputs: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sample_filter = set(sample_ids) if sample_ids else None
    system_filter = set(system_names) if system_names else None
    selected_samples = [
        row for row in samples if sample_filter is None or row["sample_id"] in sample_filter
    ]
    if limit_samples is not None:
        selected_samples = selected_samples[:limit_samples]
    selected_ids = {row["sample_id"] for row in selected_samples}
    selected_outputs = [
        row for row in outputs
        if row["sample_id"] in selected_ids
        and (system_filter is None or row["system_name"] in system_filter)
    ]
    if limit_outputs is not None:
        selected_outputs = selected_outputs[:limit_outputs]
    required = {row["sample_id"] for row in selected_outputs}
    selected_samples = [row for row in selected_samples if row["sample_id"] in required]
    if not selected_samples or not selected_outputs:
        raise ValueError("v0.6 selection produced no source/output pairs")
    return selected_samples, selected_outputs


def _manifest(
    samples_path: str, outputs_path: str, samples: list[dict[str, Any]],
    outputs: list[dict[str, Any]], client: LLMClient,
) -> dict[str, Any]:
    hashes = prompt_manifest()
    return {
        "protocol_version": PROTOCOL_VERSION_V06,
        "implementation_version": IMPLEMENTATION_VERSION_V06,
        "implementation_hash": _implementation_hash(),
        "samples_sha256": _file_hash(samples_path),
        "outputs_sha256": _file_hash(outputs_path),
        "selected_sample_ids": [row["sample_id"] for row in samples],
        "selected_output_keys": [[row["sample_id"], row["system_name"]] for row in outputs],
        "prompt_hashes": {name: hashes[name] for name in V06_PROMPTS},
        "provider": client.provider_name,
        "model": client.model_name,
        "dimension_weights": DIMENSION_WEIGHTS_V06,
    }


def _assert_resume_compatible(existing: dict[str, Any], current: dict[str, Any]) -> None:
    changed = [key for key, value in current.items() if existing.get(key) != value]
    if changed:
        raise ValueError("Cannot resume v0.6 run because configuration changed: " + ", ".join(changed))


def _validate_resume_cards(
    samples: list[dict[str, Any]], source_cards: dict[str, dict[str, Any]],
    reference_cards: dict[str, dict[str, Any]],
    evaluation_contexts: dict[str, dict[str, Any]],
) -> None:
    sample_by_id = {row["sample_id"]: row for row in samples}
    if (
        set(source_cards) - set(sample_by_id)
        or set(reference_cards) - set(sample_by_id)
        or set(evaluation_contexts) - set(sample_by_id)
    ):
        raise ValueError("v0.6 resume cards contain unexpected sample IDs")
    for sample_id, card in source_cards.items():
        if card.get("source_text") != sample_by_id[sample_id]["source_text"]:
            raise ValueError(f"v0.6 source card text mismatch for {sample_id}")
        issues = validate_source_card_v06(card)
        expected = str(card.get("metadata", {}).get("source_card_hash") or "")
        if issues or expected != artifact_hash(card):
            raise ValueError(f"invalid v0.6 source resume card for {sample_id}: {'; '.join(issues)}")
    for sample_id, card in reference_cards.items():
        source_card = source_cards.get(sample_id)
        if source_card is None:
            raise ValueError(f"reference resume card has no source card for {sample_id}")
        if card.get("target_translation") != sample_by_id[sample_id]["reference_translation"]:
            raise ValueError(f"v0.6 reference translation mismatch for {sample_id}")
        issues = validate_projection_card_v06(card, source_card, si_mode=False)
        expected = str(card.get("metadata", {}).get("reference_card_hash") or "")
        if issues or expected != artifact_hash(card):
            raise ValueError(f"invalid v0.6 reference resume card for {sample_id}: {'; '.join(issues)}")
    for sample_id, context in evaluation_contexts.items():
        source_card = source_cards.get(sample_id)
        reference_card = reference_cards.get(sample_id)
        if source_card is None or reference_card is None:
            raise ValueError(f"evaluation context lacks frozen cards for {sample_id}")
        issues = validate_evaluation_context_v06(context, source_card, reference_card)
        if issues:
            raise ValueError(
                f"invalid v0.6 evaluation context for {sample_id}: {'; '.join(issues)}"
            )


def _validate_resume_si_results(
    outputs: list[dict[str, Any]],
    source_cards: dict[str, dict[str, Any]],
    reference_cards: dict[str, dict[str, Any]],
    evaluation_contexts: dict[str, dict[str, Any]],
    si_cards: dict[tuple[str, str], dict[str, Any]],
    results: list[dict[str, Any]],
) -> None:
    output_by_key = {
        (str(row["sample_id"]), str(row["system_name"])): row for row in outputs
    }
    if set(si_cards) - set(output_by_key):
        raise ValueError("v0.6 SI resume cards contain unexpected output identities")
    for key, card in si_cards.items():
        source_card = source_cards.get(key[0])
        reference_card = reference_cards.get(key[0])
        evaluation_context = evaluation_contexts.get(key[0])
        output = output_by_key[key]
        if source_card is None or reference_card is None or evaluation_context is None:
            raise ValueError(f"v0.6 SI resume card lacks prerequisites for {key[0]}/{key[1]}")
        if (
            card.get("sample_id") != key[0]
            or card.get("system_name") != key[1]
            or card.get("target_translation") != output["si_translation"]
            or card.get("source_card_hash") != source_card["metadata"]["source_card_hash"]
            or card.get("reference_card_hash")
            != reference_card["metadata"]["reference_card_hash"]
            or card.get("evaluation_context_hash")
            != evaluation_context["metadata"]["evaluation_context_hash"]
        ):
            raise ValueError(f"v0.6 SI resume identity/hash mismatch for {key[0]}/{key[1]}")
        issues = validate_projection_card_v06(
            card, source_card, si_mode=True, reference_card=reference_card,
            evaluation_context=evaluation_context,
        )
        issues.extend(validate_requirement_inheritance(
            card, reference_card, "anchor_projections", "source_anchor_id"
        ))
        issues.extend(validate_requirement_inheritance(
            card, reference_card, "event_projections", "source_event_id"
        ))
        expected = str(card.get("metadata", {}).get("si_card_hash") or "")
        if issues or expected != artifact_hash(card):
            raise ValueError(
                f"invalid v0.6 SI resume card for {key[0]}/{key[1]}: {'; '.join(issues)}"
            )

    result_keys: set[tuple[str, str]] = set()
    for result in results:
        key = (str(result.get("sample_id")), str(result.get("system_name")))
        if key in result_keys or key not in output_by_key or key not in si_cards:
            raise ValueError("v0.6 resume results contain duplicate or unmatched identities")
        result_keys.add(key)
        source_card = source_cards[key[0]]
        reference_card = reference_cards[key[0]]
        evaluation_context = evaluation_contexts[key[0]]
        si_card = si_cards[key]
        if (
            result.get("source_card_hash") != source_card["metadata"]["source_card_hash"]
            or result.get("reference_card_hash")
            != reference_card["metadata"]["reference_card_hash"]
            or result.get("evaluation_context_hash")
            != evaluation_context["metadata"]["evaluation_context_hash"]
            or result.get("si_card_hash") != si_card["metadata"]["si_card_hash"]
        ):
            raise ValueError(f"v0.6 resume result hash mismatch for {key[0]}/{key[1]}")
        recalculated = calculate_v06_scores(
            source_card,
            si_card,
            [row for row in result.get("fluency_issues", []) if isinstance(row, dict)],
            [row for row in result.get("si_expression_issues", []) if isinstance(row, dict)],
        )
        for field in (
            "dimension_scores", "dimension_weights", "score_diagnostics",
            "final_score", "score_status",
        ):
            if result.get(field) != recalculated[field]:
                raise ValueError(
                    f"v0.6 resume result score mismatch for {key[0]}/{key[1]}: {field}"
                )


def _remove_failure(
    rows: list[dict[str, Any]], stage: str, sample_id: str, system_name: str | None
) -> list[dict[str, Any]]:
    return [
        row for row in rows
        if not (
            row.get("stage") == stage
            and row.get("sample_id") == sample_id
            and row.get("system_name") == system_name
        )
    ]


def _deduplicate_failures(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("stage") or ""), str(row.get("sample_id") or ""),
            str(row.get("system_name") or ""),
        )
        output[key] = row
    return list(output.values())


def _implementation_hash() -> str:
    root = Path(__file__).resolve().parent
    payload = b"".join(
        (root / name).read_bytes()
        for name in ("v06_agents.py", "v06_validation.py", "v06_pipeline.py", "prompt_loader.py")
    )
    return hashlib.sha256(payload).hexdigest()


def _file_hash(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
