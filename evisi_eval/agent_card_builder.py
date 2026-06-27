from __future__ import annotations

import hashlib
import json
from typing import Any

from .llm_provider import LLMClient
from .models import FACT_TYPES


CARD_PROMPT_VERSION = "card_builder_v1.0"

CARD_SYSTEM_PROMPT = """You are the Evaluation Card Builder for a simultaneous-interpretation benchmark.

Your task is analysis, not scoring. Read the source transcript and optional offline translation, then decompose the source into independently verifiable evaluation items. The offline translation is only a target-language aid; the source transcript remains authoritative. You must never infer requirements from a tested system output.

Return one JSON object with exactly these top-level arrays:
- facts: hard factual slots. Allowed types: number, percentage, money, unit, date_time, entity, term, polarity, direction, scope, modality.
- propositions: atomic main meanings. Exclude fact values already represented in facts; link them with linked_facts.
- relations: only meaning-bearing links between propositions. Allowed types: cause, condition, contrast, concession, comparison, purpose, temporal_order, exception, attribution, enumeration.
- terminology: source terms and acceptable target-language candidates.
- allowed_omissions: fillers, abandoned false starts, low-information repetition, or procedural padding that may be omitted.
- forbidden_losses: facts, propositions, or relations whose loss changes conclusion, action, risk, eligibility, or speaker stance.

Importance is deterministic in meaning:
3 = changes identity, conclusion, action, risk, legal/medical/financial meaning, threshold, or eligibility.
2 = important support or constraint.
1 = background detail.

Every source_span and source_cue must be copied verbatim from the transcript. Do not output a score or deduction. Do not treat fluency or style as source meaning. Return JSON only.

Required item shapes:
facts: {fact_id,type,source_span,canonical_value,importance,must_preserve,acceptable_variants,notes,extraction_confidence}
propositions: {prop_id,source_span,canonical_meaning,target_reference,importance,required,linked_facts,notes,extraction_confidence}
relations: {relation_id,type,source_cues,head_prop_id,dependent_prop_id,canonical_meaning,importance,extraction_confidence}
terminology: {term_id,source_term,target_candidates,importance,required}
allowed_omissions: {source_span,reason}
forbidden_losses: {kind,ref_id,reason}
"""


def build_agent_card(sample: dict[str, Any], client: LLMClient) -> dict[str, Any]:
    transcript = str(sample.get("transcript") or sample.get("source_text") or "").strip()
    if not transcript:
        raise ValueError("Each sample must include a non-empty transcript or source_text")
    sample_id = str(sample.get("sample_id") or "").strip()
    if not sample_id:
        raise ValueError("Each sample must include sample_id")

    payload = {
        "task": "build_evaluation_card",
        "sample_id": sample_id,
        "transcript": transcript,
        "offline_translation": sample.get("offline_translation"),
        "src_lang": sample.get("src_lang", "unspecified"),
        "tgt_lang": sample.get("tgt_lang", "unspecified"),
        "domain": sample.get("domain", "unspecified"),
    }
    response = client.generate_json(CARD_SYSTEM_PROMPT, payload, task="build_evaluation_card")
    raw_card = response.data.get("evaluation_card", response.data)
    if not isinstance(raw_card, dict):
        raise ValueError("Card builder response must contain a JSON object")
    card, issues = normalize_card(raw_card, sample)
    card["metadata"] = {
        "schema_version": "1.0.0",
        "prompt_version": CARD_PROMPT_VERSION,
        "builder_provider": response.provider,
        "builder_model": response.model,
        "builder_request_id": response.request_id,
        "card_status": "draft",
        "review_required": bool(issues),
        "validation_issues": issues,
        "system_outputs_visible_to_builder": False,
    }
    card["metadata"]["card_hash"] = card_hash(card)
    return card


def normalize_card(raw: dict[str, Any], sample: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    transcript = str(sample.get("transcript") or sample.get("source_text") or "").strip()
    issues: list[str] = []

    facts: list[dict[str, Any]] = []
    for index, item in enumerate(_list(raw.get("facts")), 1):
        fact_type = str(item.get("type") or "term").strip().lower()
        if fact_type not in FACT_TYPES:
            issues.append(f"facts[{index}] has unsupported type={fact_type!r}; normalized to term")
            fact_type = "term"
        source_span = str(item.get("source_span") or "").strip()
        if not source_span:
            issues.append(f"facts[{index}] missing source_span; item dropped")
            continue
        if source_span not in transcript:
            issues.append(f"facts[{index}] source_span is not verbatim transcript text")
        importance = _importance(item.get("importance"))
        facts.append(
            {
                "fact_id": str(item.get("fact_id") or f"f_{index:03d}"),
                "type": fact_type,
                "source_span": source_span,
                "canonical_value": item.get("canonical_value", source_span),
                "importance": importance,
                "must_preserve": bool(item.get("must_preserve", importance >= 2)),
                "acceptable_variants": _strings(item.get("acceptable_variants")),
                "notes": _optional_string(item.get("notes")),
                "extraction_confidence": _confidence(item.get("extraction_confidence"), 0.8),
            }
        )
    facts = _dedupe_ids(facts, "fact_id", "f")
    fact_ids = {item["fact_id"] for item in facts}

    propositions: list[dict[str, Any]] = []
    for index, item in enumerate(_list(raw.get("propositions")), 1):
        source_span = str(item.get("source_span") or "").strip()
        if not source_span:
            issues.append(f"propositions[{index}] missing source_span; item dropped")
            continue
        if source_span not in transcript:
            issues.append(f"propositions[{index}] source_span is not verbatim transcript text")
        linked = [x for x in _strings(item.get("linked_facts")) if x in fact_ids]
        propositions.append(
            {
                "prop_id": str(item.get("prop_id") or f"p_{index:03d}"),
                "source_span": source_span,
                "canonical_meaning": str(item.get("canonical_meaning") or source_span).strip(),
                "target_reference": _optional_string(item.get("target_reference")),
                "importance": _importance(item.get("importance")),
                "required": bool(item.get("required", True)),
                "linked_facts": linked,
                "notes": _optional_string(item.get("notes")),
                "extraction_confidence": _confidence(item.get("extraction_confidence"), 0.8),
            }
        )
    if not propositions:
        issues.append("No proposition returned; inserted one document-level proposition for mandatory review")
        propositions = [
            {
                "prop_id": "p_001",
                "source_span": transcript,
                "canonical_meaning": str(sample.get("offline_translation") or transcript),
                "target_reference": _optional_string(sample.get("offline_translation")),
                "importance": 3,
                "required": True,
                "linked_facts": sorted(fact_ids),
                "notes": "Fallback item because the card model returned no propositions",
                "extraction_confidence": 0.0,
            }
        ]
    propositions = _dedupe_ids(propositions, "prop_id", "p")
    prop_ids = {item["prop_id"] for item in propositions}

    relations: list[dict[str, Any]] = []
    for index, item in enumerate(_list(raw.get("relations")), 1):
        head = str(item.get("head_prop_id") or "")
        dependent = str(item.get("dependent_prop_id") or "")
        if head not in prop_ids or dependent not in prop_ids:
            issues.append(f"relations[{index}] references unknown propositions; item dropped")
            continue
        cues = _strings(item.get("source_cues"))
        if any(cue not in transcript for cue in cues):
            issues.append(f"relations[{index}] includes a non-verbatim source cue")
        relations.append(
            {
                "relation_id": str(item.get("relation_id") or f"r_{index:03d}"),
                "type": str(item.get("type") or "unspecified").strip().lower(),
                "source_cues": cues,
                "head_prop_id": head,
                "dependent_prop_id": dependent,
                "canonical_meaning": str(item.get("canonical_meaning") or "").strip(),
                "importance": _importance(item.get("importance")),
                "extraction_confidence": _confidence(item.get("extraction_confidence"), 0.8),
            }
        )
    relations = _dedupe_ids(relations, "relation_id", "r")

    terminology = []
    for index, item in enumerate(_list(raw.get("terminology")), 1):
        source_term = str(item.get("source_term") or "").strip()
        if not source_term:
            continue
        terminology.append(
            {
                "term_id": str(item.get("term_id") or f"t_{index:03d}"),
                "source_term": source_term,
                "target_candidates": _strings(item.get("target_candidates")),
                "importance": _importance(item.get("importance")),
                "required": bool(item.get("required", True)),
            }
        )

    card = {
        "sample_id": str(sample["sample_id"]),
        "transcript": transcript,
        "source_text": transcript,
        "offline_translation": sample.get("offline_translation"),
        "domain": sample.get("domain", "unspecified"),
        "src_lang": sample.get("src_lang", "unspecified"),
        "tgt_lang": sample.get("tgt_lang", "unspecified"),
        "facts": facts,
        "propositions": propositions,
        "relations": relations,
        "terminology": terminology,
        "allowed_omissions": _simple_records(raw.get("allowed_omissions"), "source_span", "reason"),
        "forbidden_losses": _simple_records(raw.get("forbidden_losses"), "kind", "ref_id", "reason"),
    }
    return card, issues


def card_hash(card: dict[str, Any]) -> str:
    payload = {key: value for key, value in card.items() if key != "metadata"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _importance(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 2
    return min(3, max(1, parsed))


def _confidence(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return round(min(1.0, max(0.0, parsed)), 4)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dedupe_ids(items: list[dict[str, Any]], key: str, prefix: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    for index, item in enumerate(items, 1):
        item_id = str(item.get(key) or f"{prefix}_{index:03d}")
        if item_id in seen:
            item_id = f"{prefix}_{index:03d}"
        item[key] = item_id
        seen.add(item_id)
    return items


def _simple_records(value: Any, *keys: str) -> list[dict[str, Any]]:
    records = []
    for item in _list(value):
        record = {key: item.get(key) for key in keys}
        if any(v is not None and v != "" for v in record.values()):
            records.append(record)
    return records
