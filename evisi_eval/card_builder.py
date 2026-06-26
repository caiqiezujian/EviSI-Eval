from __future__ import annotations

from .models import EvaluationCard, Fact
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
    source_text = sample["source_text"]
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

    for match in find_percentages(source_text):
        add_fact("percentage", match.span, match.value, 3, "percentage or percentage-point fact")
    for match in find_money(source_text):
        add_fact("money", match.span, match.value, 3, "money fact")
    for match in find_numbers(source_text):
        add_fact("number", match.span, match.value, 2, "numeric fact")
    for match in find_dates(source_text):
        add_fact("date_time", match.span, match.value, 2, "time or date fact", variants_for_date(match.span))
    for match in find_entities(source_text):
        add_fact("entity", match.span, match.value, 3, "named entity", variants_for_entity(match.span))
    for match in find_negations(source_text):
        add_fact("polarity", match.span, match.value, 3, "negation or polarity fact")
    for match in find_enum_markers(source_text, DIRECTION_MAP):
        add_fact("direction", match.span, match.value, 3, "direction fact")
    for match in find_enum_markers(source_text, SCOPE_MAP):
        add_fact("scope", match.span, match.value, 3, "scope or boundary fact")
    for match in find_enum_markers(source_text, MODALITY_MAP):
        add_fact("modality", match.span, match.value, 2, "modality fact")

    facts = _dedupe_fact_spans(facts)

    return EvaluationCard(
        sample_id=sample["sample_id"],
        source_text=source_text,
        offline_translation=sample.get("offline_translation"),
        domain=sample.get("domain", "unspecified"),
        src_lang=sample.get("src_lang", "en"),
        tgt_lang=sample.get("tgt_lang", "zh"),
        facts=facts,
        allowed_omissions=[
            {"span": "fillers, false starts, low-information repetitions", "reason": "reasonable SI compression"}
        ],
        forbidden_losses=[
            {"kind": "critical_fact", "ref_id": fact.fact_id, "reason": fact.notes or "must preserve"}
            for fact in facts
            if fact.importance == 3
        ],
        metadata={"schema_version": "0.1.0", "builder": "rules_v0_1"},
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
