"""Prompt template loader with manifest hashing for reproducibility."""

from __future__ import annotations

import hashlib
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

# v0.4 agent prompts (3 agents + 1 repair)
PROMPT_FILES = {
    "source_worker": "source_worker.md",
    "target_worker": "target_worker.md",
    "main_agent": "main_agent.md",
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
