from __future__ import annotations

import hashlib
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

PROMPT_FILES = {
    "source_anchors": "source_anchor_extractor.md",
    "source_events": "source_event_extractor.md",
    "sentence_alignment": "sentence_aligner.md",
    "target_analysis": "target_semantic_analyzer.md",
    "semantic_alignment": "semantic_aligner.md",
    "target_delivery": "target_delivery_evaluator.md",
    "error_review": "error_reviewer.md",
    "schema_repair": "schema_repair.md",
}


def load_prompt(name: str) -> str:
    try:
        filename = PROMPT_FILES[name]
    except KeyError as exc:
        raise KeyError(f"Unknown prompt: {name}") from exc
    return (PROMPT_DIR / filename).read_text(encoding="utf-8")


def prompt_manifest() -> dict[str, str]:
    return {
        name: hashlib.sha256(load_prompt(name).encode("utf-8")).hexdigest()
        for name in sorted(PROMPT_FILES)
    }
