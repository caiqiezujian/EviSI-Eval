from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .io_utils import write_jsonl


def read_json_object_stream(path: str | Path) -> list[dict[str, Any]]:
    """Read JSONL or concatenated JSON objects from a text file."""
    text = Path(path).read_text(encoding="utf-8-sig")
    decoder = json.JSONDecoder()
    rows: list[dict[str, Any]] = []
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        if text[index] != "{":
            next_obj = text.find("{", index + 1)
            if next_obj == -1:
                break
            index = next_obj
        obj, end = decoder.raw_decode(text, index)
        if not isinstance(obj, dict):
            raise ValueError(f"Expected JSON object in {path}")
        rows.append(obj)
        index = end
    return rows


def convert_wide_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    samples: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    for row in rows:
        sample_id = row.get("vid") or row.get("sample_id")
        if not sample_id:
            raise ValueError("Each row must include vid or sample_id")
        transcript = row.get("transcript")
        if not transcript:
            raise ValueError(f"Row {sample_id} is missing transcript")
        sample = {
            "sample_id": sample_id,
            "transcript": transcript,
            "offline_translation": row.get("translation"),
            "domain": _infer_domain(sample_id),
            "src_lang": _infer_src_lang(sample_id),
            "tgt_lang": _infer_tgt_lang(sample_id),
            "source_format": "wide_system_transcript",
        }
        samples.append(sample)

        for key, value in sorted(row.items()):
            if not key.endswith("_trans") or key == "translation" or not value:
                continue
            system_name = key[: -len("_trans")]
            output = {
                "sample_id": sample_id,
                "system_name": system_name,
                "si_translation": value,
            }
            asr = row.get(f"{system_name}_asr")
            if asr:
                output["system_asr"] = asr
            outputs.append(output)
    return samples, outputs


def import_wide_files(input_paths: list[str | Path], samples_output: str | Path, outputs_output: str | Path) -> dict:
    all_rows: list[dict[str, Any]] = []
    for path in input_paths:
        all_rows.extend(read_json_object_stream(path))
    samples, outputs = convert_wide_rows(all_rows)
    write_jsonl(samples_output, samples)
    write_jsonl(outputs_output, outputs)
    return {
        "input_files": [str(p) for p in input_paths],
        "samples": len(samples),
        "outputs": len(outputs),
        "systems": sorted({row["system_name"] for row in outputs}),
        "samples_output": str(samples_output),
        "outputs_output": str(outputs_output),
    }


def _infer_domain(sample_id: str) -> str:
    parts = sample_id.split("-")
    if len(parts) >= 3:
        tail = "-".join(parts[2:])
        return tail.split("_")[0]
    return "unspecified"


def _infer_src_lang(sample_id: str) -> str:
    prefix = sample_id.split("-")[0]
    if "2" in prefix:
        return prefix.split("2")[0] or "unspecified"
    return "unspecified"


def _infer_tgt_lang(sample_id: str) -> str:
    prefix = sample_id.split("-")[0]
    if "2" in prefix:
        return prefix.split("2", 1)[1] or "unspecified"
    return "unspecified"

