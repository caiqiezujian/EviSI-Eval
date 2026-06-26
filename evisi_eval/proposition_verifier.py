from __future__ import annotations

import re
from typing import Any

from .models import PropositionVerdict
from .normalization import normalize_simple


def verify_proposition(prop: dict[str, Any], si_translation: str, mode: str) -> PropositionVerdict:
    source_span = prop.get("source_span", "")
    target_reference = prop.get("target_reference")
    reference = target_reference or source_span

    if target_reference:
        return _verify_against_reference(prop, si_translation, reference)

    if _same_script(source_span, si_translation):
        return _verify_against_reference(prop, si_translation, source_span)

    return PropositionVerdict(
        prop_id=prop["prop_id"],
        source_span=source_span,
        target_reference=target_reference,
        matched_target_span=None,
        verdict="ambiguous",
        confidence=0.45,
        deduction=0.0,
        severity="none",
        evidence_text="source-only cross-lingual proposition requires LLM or human review",
        reason=f"{mode} mode has no target-side reference for semantic equivalence",
        review_required=True,
    )


def _verify_against_reference(prop: dict[str, Any], target: str, reference: str) -> PropositionVerdict:
    score = _similarity(reference, target)
    importance = int(prop.get("importance", 2))
    if score >= 0.72:
        verdict = "covered"
        confidence = min(0.95, score)
        deduction = 0.0
        severity = "none"
        reason = "reference meaning appears covered"
        review_required = False
    elif score >= 0.45:
        verdict = "partially_covered"
        confidence = score
        deduction = {1: 1.5, 2: 3.0, 3: 5.0}[importance]
        severity = "major" if importance >= 2 else "minor"
        reason = "reference meaning partially overlaps target"
        review_required = importance >= 2
    else:
        verdict = "missing_or_contradicted"
        confidence = 1 - score
        deduction = {1: 2.0, 2: 4.0, 3: 8.0}[importance]
        severity = "critical" if importance == 3 else "major"
        reason = "reference meaning is not covered by target"
        review_required = True

    return PropositionVerdict(
        prop_id=prop["prop_id"],
        source_span=prop.get("source_span", ""),
        target_reference=prop.get("target_reference"),
        matched_target_span=target if target else None,
        verdict=verdict,
        confidence=round(confidence, 3),
        deduction=deduction,
        severity=severity,
        evidence_text=f"similarity={score:.3f}; reference={reference}",
        reason=reason,
        review_required=review_required,
    )


def _similarity(reference: str, target: str) -> float:
    ref_tokens = _tokens(reference)
    tgt_tokens = _tokens(target)
    if not ref_tokens or not tgt_tokens:
        return 0.0
    inter = len(ref_tokens & tgt_tokens)
    union = len(ref_tokens | tgt_tokens)
    return inter / union if union else 0.0


def _tokens(text: str) -> set[str]:
    text = text or ""
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    words = re.findall(r"[A-Za-z0-9%$]+", text.casefold())
    if cjk:
        # Character-level tokens are intentionally conservative for Chinese.
        return set(cjk) | set(words)
    return {normalize_simple(w) for w in words if normalize_simple(w)}


def _same_script(a: str, b: str) -> bool:
    return _has_cjk(a) == _has_cjk(b)


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))

