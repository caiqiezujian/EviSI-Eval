from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .io_utils import read_jsonl, write_json, write_jsonl


def prepare_dataset(samples_path: str, outputs_path: str, output_dir: str) -> dict[str, Any]:
    samples = [_sample(row) for row in read_jsonl(samples_path)]
    outputs = [_output(row) for row in read_jsonl(outputs_path)]
    _validate(samples, outputs)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    write_jsonl(root / "source_00_input.jsonl", samples)
    write_jsonl(root / "target_00_input.jsonl", outputs)

    by_sample: dict[str, list[dict[str, Any]]] = {row["sample_id"]: [] for row in samples}
    for output in outputs:
        by_sample[output["sample_id"]].append(output)
    sample_root = root / "samples"
    for sample in samples:
        folder = sample_root / _safe_name(sample["sample_id"])
        write_json(folder / "source.json", sample)
        write_jsonl(folder / "system_outputs.jsonl", by_sample[sample["sample_id"]])

    first_sample = samples[0]
    first_output = next(row for row in outputs if row["sample_id"] == first_sample["sample_id"])
    smoke_dir = root / "smoke"
    write_jsonl(smoke_dir / "source_00_input.jsonl", [first_sample])
    write_jsonl(smoke_dir / "target_00_input.jsonl", [first_output])

    manifest = {
        "samples": len(samples),
        "outputs": len(outputs),
        "systems": sorted({row["system_name"] for row in outputs}),
        "smoke_sample_id": first_sample["sample_id"],
        "smoke_system_name": first_output["system_name"],
        "source_input": str(root / "source_00_input.jsonl"),
        "target_input": str(root / "target_00_input.jsonl"),
    }
    write_json(root / "dataset_manifest.json", manifest)
    (root / "README.md").write_text(
        "# EviSI-Eval v0.7 标准化测试数据\n\n"
        "- `source_00_input.jsonl`：全部源文，每个 sample 只出现一次。\n"
        "- `target_00_input.jsonl`：全部同传最终译文。\n"
        "- `samples/<sample_id>/`：按样本拆分，便于人工查看。\n"
        "- `smoke/`：第一条源文和第一条系统译文，用于低成本端到端测试。\n\n"
        "`system_asr` 不进入评测；`reference_translation` 仅保留在输入中，不传入核心评测阶段。\n",
        encoding="utf-8",
    )
    return manifest


def _sample(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": str(row.get("sample_id") or row.get("vid") or "").strip(),
        "source_text": str(row.get("source_text") or row.get("transcript") or ""),
        "reference_translation": row.get("reference_translation", row.get("offline_translation")),
        "src_lang": str(row.get("src_lang") or "unspecified"),
        "tgt_lang": str(row.get("tgt_lang") or "unspecified"),
        "domain": str(row.get("domain") or "unspecified"),
    }


def _output(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": str(row.get("sample_id") or row.get("vid") or "").strip(),
        "system_name": str(row.get("system_name") or "").strip(),
        "si_translation": str(row.get("si_translation") or ""),
    }


def _validate(samples: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> None:
    sample_ids = [row["sample_id"] for row in samples]
    if not samples or any(not value for value in sample_ids) or len(sample_ids) != len(set(sample_ids)):
        raise ValueError("samples need unique non-empty sample_id values")
    if any(not row["source_text"].strip() for row in samples):
        raise ValueError("every sample needs non-empty source_text")
    valid_ids = set(sample_ids)
    keys = []
    for row in outputs:
        if row["sample_id"] not in valid_ids or not row["system_name"] or not row["si_translation"].strip():
            raise ValueError("every output must reference a sample and contain system_name/si_translation")
        keys.append((row["sample_id"], row["system_name"]))
    if not outputs or len(keys) != len(set(keys)):
        raise ValueError("outputs need unique (sample_id, system_name) pairs")


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)
