"""Extraction-only pipeline for source semantics, alignment, and target semantics."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .agents import AlignmentAgent, SourceCardAgent, TargetEvidenceAgent
from .config import get_provider_config
from .io_utils import append_jsonl, read_json, read_jsonl, write_json, write_jsonl
from .llm_provider import HTTPJSONClient, LLMClient
from .prompt_loader import prompt_manifest
from .validation import (
    PROTOCOL_VERSION,
    validate_alignment_artifact,
    validate_source_card_artifact,
    validate_target_evidence_artifact,
)


EXTRACTION_IMPLEMENTATION_VERSION = "0.5.0-semantic-v2"


def run_extraction_pipeline(
    samples_path: str,
    outputs_path: str,
    output_dir: str = "results",
    run_name: str = "semantic_extraction",
    provider_name: str = "deepseek",
    resume: bool = False,
    limit_samples: int | None = None,
    limit_outputs: int | None = None,
    client: LLMClient | None = None,
) -> dict[str, Any]:
    samples = [_normalize_sample(row) for row in read_jsonl(samples_path)]
    outputs = [_normalize_output(row) for row in read_jsonl(outputs_path)]
    _validate_inputs(samples, outputs)
    if limit_samples is not None:
        samples = samples[:limit_samples]
    selected_ids = {row["sample_id"] for row in samples}
    outputs = [row for row in outputs if row["sample_id"] in selected_ids]
    if limit_outputs is not None:
        outputs = outputs[:limit_outputs]
    required_ids = {row["sample_id"] for row in outputs}
    samples = [row for row in samples if row["sample_id"] in required_ids]
    if not samples or not outputs:
        raise ValueError("selection produced no source/output pairs")

    if client is None:
        client = HTTPJSONClient(get_provider_config(provider_name))

    run_dir = Path(output_dir) / run_name
    paths = {
        "source_cards": run_dir / "source/source_cards.jsonl",
        "alignments": run_dir / "target/alignments.jsonl",
        "target_cards": run_dir / "target/target_semantic_cards.jsonl",
        "failures": run_dir / "failures.jsonl",
        "manifest": run_dir / "extraction_manifest.json",
        "summary": run_dir / "extraction_summary.json",
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(samples_path, outputs_path, samples, outputs, client)
    if resume:
        if not paths["manifest"].exists():
            raise ValueError(
                "Cannot resume extraction without extraction_manifest.json; "
                "use a new run-name to prevent reuse of legacy cards"
            )
        _assert_resume_compatible(read_json(paths["manifest"]), manifest)
    else:
        for key in ("source_cards", "alignments", "target_cards", "failures"):
            write_jsonl(paths[key], [])
    write_json(paths["manifest"], manifest)

    failures = read_jsonl(paths["failures"]) if resume else []
    source_cards = {
        str(row.get("sample_id")): row
        for row in (read_jsonl(paths["source_cards"]) if resume else [])
    }
    alignments = {
        (str(row.get("sample_id")), str(row.get("system_name"))): row
        for row in (read_jsonl(paths["alignments"]) if resume else [])
    }
    target_cards = {
        (str(row.get("sample_id")), str(row.get("system_name"))): row
        for row in (read_jsonl(paths["target_cards"]) if resume else [])
    }
    if resume:
        _validate_resume_artifacts(samples, outputs, source_cards, alignments, target_cards)

    source_agent = SourceCardAgent(client)
    alignment_agent = AlignmentAgent(client)
    target_agent = TargetEvidenceAgent(client)

    for sample in samples:
        sample_id = str(sample["sample_id"])
        if sample_id in source_cards:
            continue
        try:
            card, _ = source_agent.build(sample)
            source_cards[sample_id] = card
            append_jsonl(paths["source_cards"], card)
            failures = _remove_failures(failures, "source", sample_id, None)
        except Exception as exc:
            failure = {"stage": "source", "sample_id": sample_id, "error": str(exc)}
            failures.append(failure)
            append_jsonl(paths["failures"], failure)

    for output in outputs:
        sample_id = str(output["sample_id"])
        system_name = str(output["system_name"])
        key = (sample_id, system_name)
        source_card = source_cards.get(sample_id)
        if source_card is None:
            continue
        if key not in alignments:
            try:
                result = alignment_agent.align(source_card, output)
                alignment = {
                    "sample_id": sample_id,
                    "system_name": system_name,
                    "si_translation": output["si_translation"],
                    "source_card_hash": source_card["metadata"]["source_card_hash"],
                    "eval_units": result.artifact["eval_units"],
                    "metadata": {
                        "protocol_version": PROTOCOL_VERSION,
                        "agent_trace": result.traces,
                        "initial_validation_issues": result.initial_issues,
                    },
                }
                alignments[key] = alignment
                append_jsonl(paths["alignments"], alignment)
                failures = _remove_failures(failures, "alignment", sample_id, system_name)
            except Exception as exc:
                failure = {
                    "stage": "alignment", "sample_id": sample_id,
                    "system_name": system_name, "error": str(exc),
                }
                failures.append(failure)
                append_jsonl(paths["failures"], failure)
                continue

        if key in target_cards:
            continue
        alignment = alignments[key]
        try:
            result = target_agent.analyze(sample_id, alignment["eval_units"])
            target_card = {
                "sample_id": sample_id,
                "system_name": system_name,
                "si_translation": output["si_translation"],
                "source_card_hash": source_card["metadata"]["source_card_hash"],
                "eval_units": alignment["eval_units"],
                "target_anchors": result.artifact["target_anchors"],
                "target_events": result.artifact["target_events"],
                "target_relations": result.artifact["target_relations"],
                "metadata": {
                    "protocol_version": PROTOCOL_VERSION,
                    "provider": client.provider_name,
                    "model": client.model_name,
                    "system_name_visible_to_agent": False,
                    "source_semantics_visible_to_agent": False,
                    "agent_trace": result.traces,
                    "initial_validation_issues": result.initial_issues,
                    "normalization_notes": result.normalization_notes,
                },
            }
            target_cards[key] = target_card
            append_jsonl(paths["target_cards"], target_card)
            failures = _remove_failures(failures, "target", sample_id, system_name)
        except Exception as exc:
            failure = {
                "stage": "target", "sample_id": sample_id,
                "system_name": system_name, "error": str(exc),
            }
            failures.append(failure)
            append_jsonl(paths["failures"], failure)

    write_jsonl(paths["failures"], failures)
    summary = {
        "protocol_version": PROTOCOL_VERSION,
        "implementation_version": EXTRACTION_IMPLEMENTATION_VERSION,
        "source_cards": len(source_cards),
        "alignments": len(alignments),
        "target_cards": len(target_cards),
        "failures": len(failures),
        "paths": {key: str(value) for key, value in paths.items()},
    }
    write_json(paths["summary"], summary)
    return summary


def _manifest(
    samples_path: str, outputs_path: str, samples: list[dict[str, Any]],
    outputs: list[dict[str, Any]], client: LLMClient,
) -> dict[str, Any]:
    hashes = prompt_manifest()
    return {
        "protocol_version": PROTOCOL_VERSION,
        "implementation_version": EXTRACTION_IMPLEMENTATION_VERSION,
        "implementation_sha256": _implementation_hash(),
        "samples_sha256": _file_hash(samples_path),
        "outputs_sha256": _file_hash(outputs_path),
        "selected_sample_ids": [row["sample_id"] for row in samples],
        "selected_output_keys": [[row["sample_id"], row["system_name"]] for row in outputs],
        "prompt_hashes": {
            key: hashes[key]
            for key in ("source_evidence_agent", "alignment_agent", "target_evidence_agent", "schema_repair")
        },
        "provider": client.provider_name,
        "model": client.model_name,
    }


def _assert_resume_compatible(existing: dict[str, Any], current: dict[str, Any]) -> None:
    changed = [key for key, value in current.items() if existing.get(key) != value]
    if changed:
        raise ValueError("Cannot resume extraction because configuration changed: " + ", ".join(changed))


def _validate_resume_artifacts(
    samples: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    source_cards: dict[str, dict[str, Any]],
    alignments: dict[tuple[str, str], dict[str, Any]],
    target_cards: dict[tuple[str, str], dict[str, Any]],
) -> None:
    sample_by_id = {str(row["sample_id"]): row for row in samples}
    output_by_key = {
        (str(row["sample_id"]), str(row["system_name"])): row for row in outputs
    }
    unexpected_sources = sorted(set(source_cards) - set(sample_by_id))
    unexpected_alignments = sorted(set(alignments) - set(output_by_key))
    unexpected_targets = sorted(set(target_cards) - set(output_by_key))
    if unexpected_sources or unexpected_alignments or unexpected_targets:
        raise ValueError("resume artifacts contain rows outside the current selection")

    for sample_id, card in source_cards.items():
        sample = sample_by_id[sample_id]
        if card.get("sample_id") != sample_id or card.get("source_text") != sample["source_text"]:
            raise ValueError(f"resume source card identity/text mismatch for {sample_id}")
        issues = validate_source_card_artifact(card, str(sample["source_text"]))
        expected_hash = str(card.get("metadata", {}).get("source_card_hash") or "")
        payload = {key: value for key, value in card.items() if key != "metadata"}
        actual_hash = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        if issues or not expected_hash or expected_hash != actual_hash:
            detail = "; ".join(issues) if issues else "source_card_hash mismatch"
            raise ValueError(f"resume source card failed current protocol for {sample_id}: {detail}")

    for key, alignment in alignments.items():
        output = output_by_key[key]
        source_card = source_cards.get(key[0])
        if source_card is None:
            raise ValueError(f"resume alignment has no validated source card for {key[0]}/{key[1]}")
        if (
            alignment.get("sample_id") != key[0]
            or alignment.get("system_name") != key[1]
            or alignment.get("si_translation") != output["si_translation"]
            or alignment.get("source_card_hash")
            != source_card.get("metadata", {}).get("source_card_hash")
        ):
            raise ValueError(f"resume alignment identity/hash mismatch for {key[0]}/{key[1]}")
        issues = validate_alignment_artifact(
            {"eval_units": alignment.get("eval_units")},
            source_card["source_units"],
            str(output["si_translation"]),
        )
        if issues:
            raise ValueError(
                f"resume alignment failed current protocol for {key[0]}/{key[1]}: "
                + "; ".join(issues)
            )

    for key, target_card in target_cards.items():
        output = output_by_key[key]
        source_card = source_cards.get(key[0])
        alignment = alignments.get(key)
        if source_card is None or alignment is None:
            raise ValueError(f"resume target card is missing prerequisites for {key[0]}/{key[1]}")
        if (
            target_card.get("sample_id") != key[0]
            or target_card.get("system_name") != key[1]
            or target_card.get("si_translation") != output["si_translation"]
            or target_card.get("source_card_hash")
            != source_card.get("metadata", {}).get("source_card_hash")
            or target_card.get("eval_units") != alignment.get("eval_units")
        ):
            raise ValueError(f"resume target card identity/hash mismatch for {key[0]}/{key[1]}")
        target_units = [
            {"eval_unit_id": row.get("eval_unit_id"), "target_unit": row.get("target_unit", "")}
            for row in alignment.get("eval_units", [])
            if isinstance(row, dict)
        ]
        issues = validate_target_evidence_artifact(target_card, target_units)
        if issues:
            raise ValueError(
                f"resume target card failed current protocol for {key[0]}/{key[1]}: "
                + "; ".join(issues)
            )


def _remove_failures(
    rows: list[dict[str, Any]], stage: str, sample_id: str, system_name: str | None,
) -> list[dict[str, Any]]:
    return [
        row for row in rows
        if not (
            row.get("stage") == stage
            and row.get("sample_id") == sample_id
            and row.get("system_name") == system_name
        )
    ]


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
    if not samples or any(not item for item in sample_ids) or len(sample_ids) != len(set(sample_ids)):
        raise ValueError("samples need unique non-empty sample_id values")
    if any(not row["source_text"].strip() for row in samples):
        raise ValueError("every sample needs source_text")
    valid_ids = set(sample_ids)
    keys = []
    for row in outputs:
        if row["sample_id"] not in valid_ids or not row["system_name"] or not row["si_translation"].strip():
            raise ValueError("every output must reference a sample and contain system_name/si_translation")
        keys.append((row["sample_id"], row["system_name"]))
    if not outputs or len(keys) != len(set(keys)):
        raise ValueError("outputs need unique (sample_id, system_name) pairs")


def _file_hash(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _implementation_hash() -> str:
    root = Path(__file__).resolve().parent
    payload = b"".join(
        (root / name).read_bytes()
        for name in ("extraction_pipeline.py", "agents.py", "validation.py", "prompt_loader.py")
    )
    return hashlib.sha256(payload).hexdigest()
