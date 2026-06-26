from __future__ import annotations

from decimal import Decimal
from typing import Any

from .models import Fact, FactVerdict
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
    normalize_simple,
)


def verify_fact(fact: Fact, si_translation: str) -> FactVerdict:
    if fact.type in {"number", "percentage", "money", "date_time"}:
        return _verify_value_fact(fact, si_translation)
    if fact.type in {"entity", "term"}:
        return _verify_text_fact(fact, si_translation)
    if fact.type == "polarity":
        return _verify_marker_fact(fact, si_translation, "polarity", {"negated": [m.span for m in find_negations(si_translation)]})
    if fact.type == "direction":
        found = _found_enum(si_translation, DIRECTION_MAP)
        return _verify_marker_fact(fact, si_translation, "direction", found)
    if fact.type == "scope":
        found = _found_enum(si_translation, SCOPE_MAP)
        return _verify_marker_fact(fact, si_translation, "scope", found)
    if fact.type == "modality":
        found = _found_enum(si_translation, MODALITY_MAP)
        return _verify_marker_fact(fact, si_translation, "modality", found)
    return _base_verdict(fact, None, None, "ambiguous", 0.5, "unknown fact type", "unknown fact type")


def _verify_value_fact(fact: Fact, text: str) -> FactVerdict:
    matches = _matches_for_type(fact.type, text)
    expected = _value_key(fact.canonical_value)
    exact_variant = _find_acceptable_variant(fact, text)
    if exact_variant:
        return _base_verdict(fact, exact_variant, fact.canonical_value, "correct", 0.98, "exact acceptable variant found", "exact or accepted value match")

    for span, value in matches:
        if _value_key(value) == expected:
            return _base_verdict(fact, span, value, "correct", 0.96, "normalized value matched", "normalized value match")

    if matches:
        span, value = matches[0]
        return _base_verdict(fact, span, value, "incorrect", 0.92, f"expected {fact.source_span}, found {span}", "same fact type found with different value")
    return _base_verdict(fact, None, None, "missing", 0.84, f"no candidate span found for {fact.source_span}", "required value missing")


def _verify_text_fact(fact: Fact, text: str) -> FactVerdict:
    exact_variant = _find_acceptable_variant(fact, text)
    if exact_variant:
        return _base_verdict(fact, exact_variant, fact.canonical_value, "correct", 0.97, "acceptable text variant found", "accepted entity or term variant")

    target_entities = find_entities(text)
    if fact.type == "entity" and target_entities:
        span = target_entities[0].span
        return _base_verdict(fact, span, normalize_simple(span), "incorrect", 0.86, f"expected {fact.source_span}, found {span}", "possible entity mismatch")
    return _base_verdict(fact, None, None, "missing", 0.78, f"no accepted variant found for {fact.source_span}", "entity or term missing")


def _verify_marker_fact(fact: Fact, text: str, label: str, found: dict[str, list[str]]) -> FactVerdict:
    found = {_value_key(value): spans for value, spans in found.items() if spans}
    expected = _value_key(fact.canonical_value)
    if expected in found and found[expected]:
        return _base_verdict(fact, found[expected][0], expected, "correct", 0.93, f"{label} marker preserved", "marker value match")
    if found:
        first_value, spans = next(iter(found.items()))
        return _base_verdict(fact, spans[0], first_value, "incorrect", 0.86, f"expected {expected}, found {first_value}", f"{label} value changed")
    return _base_verdict(fact, None, None, "missing", 0.80, f"no {label} marker found", f"{label} marker missing")


def _matches_for_type(kind: str, text: str) -> list[tuple[str, Any]]:
    if kind == "percentage":
        return [(m.span, m.value) for m in find_percentages(text)]
    if kind == "money":
        return [(m.span, m.value) for m in find_money(text)]
    if kind == "number":
        return [(m.span, m.value) for m in find_numbers(text)]
    if kind == "date_time":
        return [(m.span, m.value) for m in find_dates(text)]
    return []


def _find_acceptable_variant(fact: Fact, text: str) -> str | None:
    text_norm = normalize_simple(text)
    variants = [fact.source_span] + list(fact.acceptable_variants or [])
    if isinstance(fact.canonical_value, str):
        variants.append(fact.canonical_value)
    for variant in variants:
        if variant and normalize_simple(str(variant)) in text_norm:
            return str(variant)
    return None


def _found_enum(text: str, mapping: dict[str, str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for match in find_enum_markers(text, mapping):
        found.setdefault(str(match.value), []).append(match.span)
    return found


def _value_key(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value.normalize())
    if isinstance(value, dict):
        return "|".join(f"{k}:{_value_key(v)}" for k, v in sorted(value.items()))
    if isinstance(value, list):
        return "|".join(_value_key(v) for v in value)
    return normalize_simple(str(value))


def _base_verdict(
    fact: Fact,
    target_span: str | None,
    normalized_target_value: Any,
    verdict: str,
    confidence: float,
    evidence: str,
    reason: str,
) -> FactVerdict:
    severity = _severity(fact, verdict)
    deduction = _deduction(fact.importance, verdict, severity)
    cap = _cap_trigger(fact, verdict, severity)
    return FactVerdict(
        fact_id=fact.fact_id,
        type=fact.type,
        source_span=fact.source_span,
        canonical_value=fact.canonical_value,
        importance=fact.importance,
        must_preserve=fact.must_preserve,
        translation_span=target_span,
        normalized_translation_value=normalized_target_value,
        verdict=verdict,
        confidence=confidence,
        deduction=deduction,
        severity=severity,
        evidence_text=evidence,
        reason=reason,
        review_required=confidence < 0.85 or cap is not None or (fact.importance >= 3 and verdict != "correct"),
        cap_trigger=cap,
    )


def _severity(fact: Fact, verdict: str) -> str:
    if verdict == "correct":
        return "none"
    if verdict == "ambiguous":
        return "minor"
    if fact.importance == 3 and fact.type in {"entity", "percentage", "money", "number", "polarity", "direction", "scope", "modality"}:
        return "critical"
    if fact.importance >= 2:
        return "major"
    return "minor"


def _deduction(importance: int, verdict: str, severity: str) -> float:
    if verdict == "correct":
        return 0.0
    if verdict == "ambiguous":
        return {1: 1, 2: 1, 3: 2}[importance]
    if verdict == "missing":
        return {1: 2, 2: 3, 3: 4}[importance]
    if severity == "critical":
        return {1: 5, 2: 8, 3: 12}[importance]
    if severity == "major":
        return {1: 3, 2: 5, 3: 8}[importance]
    return {1: 2, 2: 3, 3: 5}[importance]


def _cap_trigger(fact: Fact, verdict: str, severity: str) -> str | None:
    if verdict == "correct" or severity != "critical":
        return None
    if fact.type in {"entity", "term"}:
        return "critical_entity_mismatch"
    if fact.type in {"polarity", "direction", "scope", "modality"}:
        return f"critical_{fact.type}_error"
    if fact.type in {"number", "percentage", "money", "unit", "date_time"}:
        return "critical_number_time_value_error"
    return "critical_fact_error"
