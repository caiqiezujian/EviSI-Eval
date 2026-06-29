from __future__ import annotations

import hashlib
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

PROMPT_FILES = {
    "source_sentence_segmentation": "source_sentence_segmentation_prompt.md",
    "source_anchor_extraction": "source_anchor_extraction_prompt.md",
    "source_event_extraction": "source_event_extraction_prompt.md",
    "source_relation_extraction": "source_relation_extraction_prompt.md",
    "target_aligned_segmentation": "target_aligned_segmentation_prompt.md",
    "target_anchor_extraction": "target_anchor_extraction_prompt.md",
    "target_event_extraction": "target_event_extraction_prompt.md",
    "target_relation_extraction": "target_relation_extraction_prompt.md",
    "fluency_evaluation": "fluency_evaluation_prompt.md",
    "si_expression_evaluation": "si_expression_evaluation_prompt.md",
    "anchor_judgement": "anchor_judgement_prompt.md",
    "event_judgement": "event_judgement_prompt.md",
    "relation_judgement": "relation_judgement_prompt.md",
    "global_fidelity_review": "global_fidelity_review_prompt.md",
    "dimension_scoring": "dimension_scoring_prompt.md",
    "final_summary": "final_summary_prompt.md",
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
