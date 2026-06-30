"""Prompt template loader with manifest hashing for reproducibility."""

from __future__ import annotations

import hashlib
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
SHARED_SEMANTIC_PROTOCOL = "semantic_extraction_protocol.md"
SEMANTIC_AGENT_PROMPTS = {"source_evidence_agent", "target_evidence_agent"}

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
    "v06_source_segment_agent": "v06_source_segment_agent.md",
    "v06_source_anchor_agent": "v06_source_anchor_agent.md",
    "v06_source_event_agent": "v06_source_event_agent.md",
    "v06_source_relation_agent": "v06_source_relation_agent.md",
    "v06_target_alignment_agent": "v06_target_alignment_agent.md",
    "v06_reference_anchor_projection_agent": "v06_reference_anchor_projection_agent.md",
    "v06_reference_event_projection_agent": "v06_reference_event_projection_agent.md",
    "v06_reference_relation_projection_agent": "v06_reference_relation_projection_agent.md",
    "v06_si_anchor_projection_agent": "v06_si_anchor_projection_agent.md",
    "v06_si_event_projection_agent": "v06_si_event_projection_agent.md",
    "v06_si_relation_projection_agent": "v06_si_relation_projection_agent.md",
}

V06_PROMPT_COMPONENTS = {
    "v06_source_anchor_agent": ("v06_anchor_protocol.md",),
    "v06_reference_anchor_projection_agent": (
        "v06_anchor_protocol.md", "v06_projection_protocol.md",
    ),
    "v06_si_anchor_projection_agent": (
        "v06_anchor_protocol.md", "v06_projection_protocol.md",
    ),
    "v06_source_event_agent": ("v06_event_protocol.md",),
    "v06_reference_event_projection_agent": (
        "v06_event_protocol.md", "v06_projection_protocol.md",
    ),
    "v06_si_event_projection_agent": (
        "v06_event_protocol.md", "v06_projection_protocol.md",
    ),
    "v06_source_relation_agent": ("v06_relation_protocol.md",),
    "v06_reference_relation_projection_agent": (
        "v06_relation_protocol.md", "v06_projection_protocol.md",
    ),
    "v06_si_relation_projection_agent": (
        "v06_relation_protocol.md", "v06_projection_protocol.md",
    ),
}


def load_prompt(name: str) -> str:
    """Load a prompt template by name. Raises KeyError if unknown."""
    try:
        filename = PROMPT_FILES[name]
    except KeyError as exc:
        raise KeyError(f"Unknown prompt: {name}") from exc
    prompt = (PROMPT_DIR / filename).read_text(encoding="utf-8")
    if name in V06_PROMPT_COMPONENTS:
        components = [
            (PROMPT_DIR / component).read_text(encoding="utf-8")
            for component in V06_PROMPT_COMPONENTS[name]
        ]
        return "\n\n---\n\n".join([*components, prompt])
    if name in SEMANTIC_AGENT_PROMPTS:
        shared_path = PROMPT_DIR / SHARED_SEMANTIC_PROTOCOL
        if shared_path.exists():
            shared = shared_path.read_text(encoding="utf-8")
            return shared + "\n\n---\n\n" + prompt
    return prompt


def prompt_manifest() -> dict[str, str]:
    """Return SHA-256 hashes of all loaded prompts for run reproducibility."""
    return {
        name: hashlib.sha256(load_prompt(name).encode("utf-8")).hexdigest()
        for name in sorted(PROMPT_FILES)
    }
