from __future__ import annotations

import re

from .models import EvaluationCard, Fact, Proposition
from .normalization import (
    DIRECTION_MAP,
    MODALITY_MAP,
    SCOPE_MAP,
    find_dates,
    find_entities,
    find_enum_markers,
    find_money,
    find_negations,
    find_numbers,
    find_percentages,
    variants_for_date,
    variants_for_entity,
)


def build_card(sample: dict) -> EvaluationCard:
    transcript = sample.get("transcript") or sample.get("source_text")
    if not transcript:
        raise ValueError("Each sample must include transcript or source_text")
    offline_translation = sample.get("offline_translation")
    evaluation_mode = "reference_assisted" if offline_translation else "source_only"
    facts: list[Fact] = []
    counters: dict[str, int] = {}

    def add_fact(kind: str, span: str, value, importance: int, notes: str, variants: list[str] | None = None) -> None:
        counters[kind] = counters.get(kind, 0) + 1
        fact_id = f"f_{kind}_{counters[kind]:03d}"
        facts.append(
            Fact(
                fact_id=fact_id,
                type=kind,
                source_span=span,
                canonical_value=value,
                importance=importance,
                must_preserve=importance >= 2,
                acceptable_variants=variants or [span],
                notes=notes,
            )
        )

    for match in find_percentages(transcript):
        add_fact("percentage", match.span, match.value, 3, "percentage or percentage-point fact")
    for match in find_money(transcript):
        add_fact("money", match.span, match.value, 3, "money fact")
    for match in find_numbers(transcript):
        add_fact("number", match.span, match.value, 2, "numeric fact")
    for match in find_dates(transcript):
        add_fact("date_time", match.span, match.value, 2, "time or date fact", variants_for_date(match.span))
    for match in find_entities(transcript):
        add_fact("entity", match.span, match.value, 3, "named entity", variants_for_entity(match.span))
    for match in find_negations(transcript):
        add_fact("polarity", match.span, match.value, 3, "negation or polarity fact")
    for match in find_enum_markers(transcript, DIRECTION_MAP):
        add_fact("direction", match.span, match.value, 3, "direction fact")
    for match in find_enum_markers(transcript, SCOPE_MAP):
        add_fact("scope", match.span, match.value, 3, "scope or boundary fact")
    for match in find_enum_markers(transcript, MODALITY_MAP):
        add_fact("modality", match.span, match.value, 2, "modality fact")

    facts = _dedupe_fact_spans(facts)
    propositions = _build_minimal_propositions(transcript, offline_translation)

    return EvaluationCard(
        sample_id=sample["sample_id"],
        transcript=transcript,
        offline_translation=offline_translation,
        domain=sample.get("domain", "unspecified"),
        src_lang=sample.get("src_lang", "en"),
        tgt_lang=sample.get("tgt_lang", "zh"),
        facts=facts,
        propositions=[p.to_dict() for p in propositions],
        allowed_omissions=[
            {"span": "fillers, false starts, low-information repetitions", "reason": "reasonable SI compression"}
        ],
        forbidden_losses=[
            {"kind": "critical_fact", "ref_id": fact.fact_id, "reason": fact.notes or "must preserve"}
            for fact in facts
            if fact.importance == 3
        ],
        metadata={
            "schema_version": "0.2.0",
            "builder": "rules_v0_2",
            "evaluation_mode": evaluation_mode,
            "transcript_required": True,
            "offline_translation_used": bool(offline_translation),
        },
    )


def _dedupe_fact_spans(facts: list[Fact]) -> list[Fact]:
    priority = {
        "money": 0,
        "percentage": 1,
        "date_time": 2,
        "entity": 3,
        "number": 4,
        "polarity": 5,
        "direction": 6,
        "scope": 7,
        "modality": 8,
    }
    ordered = sorted(facts, key=lambda fact: (priority.get(fact.type, 99), -len(fact.source_span)))
    kept: list[Fact] = []
    seen_spans: set[str] = set()
    for fact in ordered:
        key = fact.source_span.casefold().strip()
        if key in seen_spans:
            continue
        seen_spans.add(key)
        kept.append(fact)
    return sorted(kept, key=lambda fact: fact.fact_id)


def _build_minimal_propositions(transcript: str, offline_translation: str | None) -> list[Proposition]:
    source_units = _split_units(transcript)
    target_units = _split_units(offline_translation or "")
    propositions: list[Proposition] = []
    for index, unit in enumerate(source_units, 1):
        target_reference = target_units[index - 1] if index - 1 < len(target_units) else (offline_translation or None)
        propositions.append(
            Proposition(
                prop_id=f"p_{index:03d}",
                source_span=unit,
                canonical_meaning=target_reference or unit,
                importance=3 if len(source_units) == 1 else 2,
                required=True,
                target_reference=target_reference,
                notes="minimal proposition unit; review manually for benchmark use",
            )
        )
    return propositions


def _split_units(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in re.split(r"(?<=[。！？.!?])\s+|[；;]", text) if p.strip()]
    return parts or [text]
