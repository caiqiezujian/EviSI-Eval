"""Prompt template loader with manifest hashing for reproducibility."""

from __future__ import annotations

import hashlib
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
PROMPT_FILES = {
    # v0.7 agents — source (4)
    "v07_source_segment": "source/v07_source_segment.md",
    "v07_source_anchor": "source/v07_source_anchor.md",
    "v07_source_event": "source/v07_source_event.md",
    "v07_source_relation": "source/v07_source_relation.md",
    # v0.7 agents — reference (4)
    "v07_reference_align": "reference/v07_reference_align.md",
    "v07_reference_anchor": "reference/v07_reference_anchor.md",
    "v07_reference_event": "reference/v07_reference_event.md",
    "v07_reference_relation": "reference/v07_reference_relation.md",
    # v0.7 agents — SI (4)
    "v07_si_align": "si/v07_si_align.md",
    "v07_si_anchor_match": "si/v07_si_anchor_match.md",
    "v07_si_event_match": "si/v07_si_event_match.md",
    "v07_si_relation_match": "si/v07_si_relation_match.md",
    # Delivery
    "fluency_agent": "fluency_agent.md",
    "si_expression_agent": "si_expression_agent.md",
    # Shared
    "schema_repair": "schema_repair.md",
}


def load_prompt(name: str) -> str:
    """Load a prompt template by name. Raises KeyError if unknown."""
    try:
        filename = PROMPT_FILES[name]
    except KeyError as exc:
        raise KeyError(f"Unknown prompt: {name}") from exc
    return (PROMPT_DIR / filename).read_text(encoding="utf-8")


def prompt_manifest() -> dict[str, str]:
    """Return SHA-256 hashes of all loaded prompts for run reproducibility."""
    return {
        name: hashlib.sha256(load_prompt(name).encode("utf-8")).hexdigest()
        for name in sorted(PROMPT_FILES)
    }
