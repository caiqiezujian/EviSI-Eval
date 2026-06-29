from __future__ import annotations

import hashlib
import json
from typing import Any

from .llm_provider import LLMClient, LLMResponse
from .prompt_loader import load_prompt, prompt_manifest
from .validation import validate_source_card


CARD_SCHEMA_VERSION = "0.4.1"


def build_source_card(sample: dict[str, Any], client: LLMClient) -> dict[str, Any]:
    sample_id = _required_text(sample, "sample_id")
    source_text = str(sample.get("transcript") or sample.get("source_text") or "").strip()
    if not source_text:
        raise ValueError(f"sample {sample_id}: transcript or source_text is required")

    common = {
        "sample_id": sample_id,
        "source_text": source_text,
        "source_language": sample.get("src_lang", "unspecified"),
        "target_language": sample.get("tgt_lang", "unspecified"),
        "domain": sample.get("domain", "unspecified"),
        "offline_translation": sample.get("offline_translation"),
    }
    anchor_response = client.generate_json(
        load_prompt("source_anchors"), common, task="extract_source_anchors"
    )
    anchor_data = _unwrap(anchor_response.data, "source_analysis")
    sentences = _normalize_sentences(anchor_data.get("sentences"))
    anchors = _normalize_anchors(anchor_data.get("anchors"))
    _attach_anchor_ids(sentences, anchors)

    event_response = client.generate_json(
        load_prompt("source_events"),
        {**common, "sentences": sentences, "anchors": anchors},
        task="extract_source_events",
    )
    event_data = _unwrap(event_response.data, "source_event_analysis")
    card = {
        "sample_id": sample_id,
        "source_text": source_text,
        "offline_translation": sample.get("offline_translation"),
        "src_lang": sample.get("src_lang", "unspecified"),
        "tgt_lang": sample.get("tgt_lang", "unspecified"),
        "domain": sample.get("domain", "unspecified"),
        "sentences": sentences,
        "anchors": anchors,
        "events": _normalize_events(event_data.get("events")),
        "relations": _normalize_relations(event_data.get("relations")),
        "allowed_omissions": _normalize_omissions(event_data.get("allowed_omissions")),
    }

    initial_issues = validate_source_card(card)
    repair_response: LLMResponse | None = None
    if initial_issues:
        repair_response = client.generate_json(
            load_prompt("schema_repair"),
            {
                "artifact_type": "source_card",
                "source_text": source_text,
                "validation_issues": initial_issues,
                "json_to_repair": card,
            },
            task="repair_source_card",
        )
        repaired = _unwrap(repair_response.data, "source_card")
        card = _normalize_complete_card(repaired, card)

    final_issues = validate_source_card(card)
    if final_issues:
        raise ValueError(
            f"sample {sample_id}: source card failed deterministic validation: "
            + "; ".join(final_issues)
        )

    card["metadata"] = {
        "schema_version": CARD_SCHEMA_VERSION,
        "card_status": "machine_validated",
        "human_review_recommended": True,
        "system_outputs_visible": False,
        "provider": anchor_response.provider,
        "model": anchor_response.model,
        "request_ids": {
            "source_anchors": anchor_response.request_id,
            "source_events": event_response.request_id,
            "repair": repair_response.request_id if repair_response else None,
        },
        "initial_validation_issues": initial_issues,
        "prompt_hashes": prompt_manifest(),
    }
    card["metadata"]["card_hash"] = source_card_hash(card)
    return card


def source_card_hash(card: dict[str, Any]) -> str:
    payload = {key: value for key, value in card.items() if key != "metadata"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_complete_card(raw: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    sentences = _normalize_sentences(raw.get("sentences"))
    anchors = _normalize_anchors(raw.get("anchors"))
    _attach_anchor_ids(sentences, anchors)
    return {
        "sample_id": fallback["sample_id"],
        "source_text": fallback["source_text"],
        "offline_translation": fallback.get("offline_translation"),
        "src_lang": fallback.get("src_lang", "unspecified"),
        "tgt_lang": fallback.get("tgt_lang", "unspecified"),
        "domain": fallback.get("domain", "unspecified"),
        "sentences": sentences,
        "anchors": anchors,
        "events": _normalize_events(raw.get("events")),
        "relations": _normalize_relations(raw.get("relations")),
        "allowed_omissions": _normalize_omissions(raw.get("allowed_omissions")),
    }


def _normalize_sentences(value: Any) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_records(value), 1):
        rows.append(
            {
                "sentence_id": str(item.get("sentence_id") or f"S{index}").strip(),
                "sentence_text": str(item.get("sentence_text") or item.get("text") or "").strip(),
                "anchor_ids": _strings(item.get("anchor_ids")),
            }
        )
    return rows


def _normalize_anchors(value: Any) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_records(value), 1):
        source_span = str(item.get("source_span") or item.get("entity_text") or "").strip()
        rows.append(
            {
                "anchor_id": str(item.get("anchor_id") or item.get("occurrence_id") or f"A{index}").strip(),
                "sentence_id": str(item.get("sentence_id") or "").strip(),
                "source_span": source_span,
                "normalized_value": str(item.get("normalized_value") or item.get("normalized_entity") or source_span).strip(),
                "anchor_type": str(item.get("anchor_type") or item.get("entity_type") or "OTHER").strip().upper(),
                "role_hint": str(item.get("role_hint") or "other").strip().lower(),
                "attributes": item.get("attributes") if isinstance(item.get("attributes"), dict) else {},
                "importance": _importance(item.get("importance")),
                "required": bool(item.get("required", item.get("is_score_anchor", True))),
                "confidence": _confidence(item.get("confidence", item.get("extraction_confidence"))),
            }
        )
    return rows


def _normalize_events(value: Any) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_records(value), 1):
        rows.append(
            {
                "event_id": str(item.get("event_id") or f"V{index}").strip(),
                "sentence_id": str(item.get("sentence_id") or "").strip(),
                "evidence_spans": _strings(item.get("evidence_spans")),
                "canonical_meaning": str(item.get("canonical_meaning") or "").strip(),
                "predicate": str(item.get("predicate") or "").strip(),
                "arguments": _records(item.get("arguments")),
                "linked_anchor_ids": _strings(item.get("linked_anchor_ids")),
                "attributes": item.get("attributes") if isinstance(item.get("attributes"), dict) else {},
                "importance": _importance(item.get("importance")),
                "required": bool(item.get("required", True)),
                "confidence": _confidence(item.get("confidence")),
            }
        )
    return rows


def _normalize_relations(value: Any) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(_records(value), 1):
        rows.append(
            {
                "relation_id": str(item.get("relation_id") or f"R{index}").strip(),
                "relation_type": str(item.get("relation_type") or item.get("type") or "").strip().lower(),
                "head_event_id": str(item.get("head_event_id") or "").strip(),
                "dependent_event_id": str(item.get("dependent_event_id") or "").strip(),
                "source_cues": _strings(item.get("source_cues")),
                "canonical_meaning": str(item.get("canonical_meaning") or "").strip(),
                "importance": _importance(item.get("importance")),
                "required": bool(item.get("required", True)),
                "confidence": _confidence(item.get("confidence")),
            }
        )
    return rows


def _normalize_omissions(value: Any) -> list[dict[str, Any]]:
    return [
        {"source_span": str(item.get("source_span") or "").strip(), "reason": str(item.get("reason") or "").strip()}
        for item in _records(value)
    ]


def _attach_anchor_ids(sentences: list[dict[str, Any]], anchors: list[dict[str, Any]]) -> None:
    by_sentence: dict[str, list[str]] = {item["sentence_id"]: [] for item in sentences}
    for anchor in anchors:
        by_sentence.setdefault(anchor["sentence_id"], []).append(anchor["anchor_id"])
    for sentence in sentences:
        sentence["anchor_ids"] = by_sentence.get(sentence["sentence_id"], [])


def _unwrap(data: dict[str, Any], key: str) -> dict[str, Any]:
    nested = data.get(key)
    return nested if isinstance(nested, dict) else data


def _importance(value: Any) -> int:
    if isinstance(value, str):
        mapped = {"high": 3, "medium": 2, "low": 1}.get(value.strip().lower())
        if mapped:
            return mapped
    try:
        return min(3, max(1, int(value)))
    except (TypeError, ValueError):
        return 2


def _confidence(value: Any) -> float:
    try:
        return round(min(1.0, max(0.0, float(value))), 4)
    except (TypeError, ValueError):
        return 0.0


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _required_text(row: dict[str, Any], key: str) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value
