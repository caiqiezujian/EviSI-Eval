"""Prompt template loader with manifest hashing for reproducibility."""

from __future__ import annotations

import hashlib
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

PROMPT_FILES = {
    "source_evidence_agent": "source_evidence_agent.md",
    "alignment_agent": "alignment_agent.md",
    "target_evidence_agent": "target_evidence_agent.md",
    "fluency_agent": "fluency_agent.md",
    "si_expression_agent": "si_expression_agent.md",
    "primary_judge_agent": "primary_judge_agent.md",
    "reviewer_agent": "reviewer_agent.md",
    "adjudicator_agent": "adjudicator_agent.md",
    "summary_agent": "summary_agent.md",
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
