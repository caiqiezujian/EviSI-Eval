from __future__ import annotations

from typing import Any


ANCHOR_TYPES = {
    "PERSON", "ORG", "GPE", "LOCATION", "TIME", "DATE", "QUANTITY", "MONEY",
    "PERCENT", "PRODUCT", "NAMED_EVENT", "LAW_POLICY", "PROJECT", "TECH_TERM",
    "DOMAIN_TERM", "KEY_CONCEPT", "OTHER",
}
RELATION_TYPES = {
    "cause", "condition", "contrast", "concession", "comparison", "purpose",
    "temporal_order", "exception", "attribution", "enumeration",
}
FLUENCY_TYPES = {
    "grammar_error", "sentence_fragment", "source_language_residue", "unnatural_collocation",
    "unclear_reference", "register_mismatch", "unintelligible_segment",
}
EFFICIENCY_TYPES = {
    "meaningless_repetition", "redundant_restatement", "excessive_filler",
    "unsupported_addition", "avoidable_verbosity",
}
ALIGNMENT_TYPES = {"one_to_one", "one_to_many", "many_to_one", "omitted", "uncertain"}


def validate_source_card(card: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    source = _text(card.get("source_text"))
    if not source:
        issues.append("source_text is empty")

    sentences = _records(card.get("sentences"))
    if not sentences:
        issues.append("sentences must contain at least one source sentence")
    sentence_ids = _unique_ids(sentences, "sentence_id", "sentences", issues)
    for item in sentences:
        _verbatim(item.get("sentence_text"), source, f"sentence {item.get('sentence_id')}", issues)

    anchors = _records(card.get("anchors"))
    anchor_ids = _unique_ids(anchors, "anchor_id", "anchors", issues)
    for item in anchors:
        if item.get("sentence_id") not in sentence_ids:
            issues.append(f"anchor {item.get('anchor_id')} references unknown sentence")
        _verbatim(item.get("source_span"), source, f"anchor {item.get('anchor_id')}", issues)
        if item.get("anchor_type") not in ANCHOR_TYPES:
            issues.append(f"anchor {item.get('anchor_id')} has unsupported anchor_type")
        _required_field(item, "normalized_value", f"anchor {item.get('anchor_id')}", issues)
        _importance(item, f"anchor {item.get('anchor_id')}", issues)

    events = _records(card.get("events"))
    event_ids = _unique_ids(events, "event_id", "events", issues)
    for item in events:
        if item.get("sentence_id") not in sentence_ids:
            issues.append(f"event {item.get('event_id')} references unknown sentence")
        _verbatim_list(item.get("evidence_spans"), source, f"event {item.get('event_id')}", issues)
        _required_field(item, "canonical_meaning", f"event {item.get('event_id')}", issues)
        _required_field(item, "predicate", f"event {item.get('event_id')}", issues)
        for anchor_id in _strings(item.get("linked_anchor_ids")):
            if anchor_id not in anchor_ids:
                issues.append(f"event {item.get('event_id')} references unknown anchor {anchor_id}")
        for argument in _records(item.get("arguments")):
            anchor_id = argument.get("anchor_id")
            if anchor_id and anchor_id not in anchor_ids:
                issues.append(f"event {item.get('event_id')} argument references unknown anchor {anchor_id}")
            if argument.get("source_span"):
                _verbatim(argument.get("source_span"), source, f"event {item.get('event_id')} argument", issues)
        _importance(item, f"event {item.get('event_id')}", issues)

    relations = _records(card.get("relations"))
    _unique_ids(relations, "relation_id", "relations", issues)
    for item in relations:
        if item.get("relation_type") not in RELATION_TYPES:
            issues.append(f"relation {item.get('relation_id')} has unsupported relation_type")
        if item.get("head_event_id") not in event_ids or item.get("dependent_event_id") not in event_ids:
            issues.append(f"relation {item.get('relation_id')} references unknown event")
        _verbatim_list(item.get("source_cues"), source, f"relation {item.get('relation_id')}", issues, allow_empty=True)
        _importance(item, f"relation {item.get('relation_id')}", issues)

    for item in _records(card.get("allowed_omissions")):
        _verbatim(item.get("source_span"), source, "allowed omission", issues)
    return issues


def validate_sentence_alignment(
    alignment: dict[str, Any], source_sentences: list[dict[str, Any]], translation: str
) -> list[str]:
    issues: list[str] = []
    units = _records(alignment.get("target_units"))
    if not units:
        issues.append("target_units must contain at least one unit")
    unit_ids = _unique_ids(units, "unit_id", "target_units", issues)
    unit_text_by_id = {str(item.get("unit_id")): str(item.get("unit_text") or "") for item in units}
    for item in units:
        _verbatim(item.get("unit_text"), translation, f"target unit {item.get('unit_id')}", issues)

    source_by_id = {
        str(item.get("sentence_id")): str(item.get("sentence_text") or "")
        for item in source_sentences
    }
    rows = _records(alignment.get("sentence_alignments"))
    actual_ids = [str(item.get("source_sentence_id") or "") for item in rows]
    if set(actual_ids) != set(source_by_id) or len(actual_ids) != len(set(actual_ids)):
        issues.append("sentence_alignments must contain exactly one row per source sentence")

    mapped_ids: set[str] = set()
    many_groups: dict[str, list[tuple[str, ...]]] = {}
    for item in rows:
        source_id = str(item.get("source_sentence_id") or "")
        if item.get("source_sentence_text") != source_by_id.get(source_id):
            issues.append(f"sentence alignment {source_id} changed source_sentence_text")
        target_ids = _strings(item.get("target_unit_ids"))
        for target_id in target_ids:
            if target_id not in unit_ids:
                issues.append(f"sentence alignment {source_id} references unknown target unit {target_id}")
            mapped_ids.add(target_id)
        spans = _strings(item.get("target_spans"))
        _verbatim_list(spans, translation, f"sentence alignment {source_id}", issues, allow_empty=True)
        if spans != [unit_text_by_id.get(target_id, "") for target_id in target_ids]:
            issues.append(f"sentence alignment {source_id} target_spans must match referenced target units")
        alignment_type = str(item.get("alignment_type") or "")
        if alignment_type not in ALIGNMENT_TYPES:
            issues.append(f"sentence alignment {source_id} has unsupported alignment_type")
        elif alignment_type == "one_to_one" and len(target_ids) != 1:
            issues.append(f"sentence alignment {source_id} one_to_one must reference one target unit")
        elif alignment_type == "one_to_many" and len(target_ids) < 2:
            issues.append(f"sentence alignment {source_id} one_to_many must reference multiple target units")
        elif alignment_type == "many_to_one":
            if len(target_ids) != 1:
                issues.append(f"sentence alignment {source_id} many_to_one must reference one target unit")
            group_id = str(item.get("group_id") or "")
            if not group_id:
                issues.append(f"sentence alignment {source_id} many_to_one requires group_id")
            else:
                many_groups.setdefault(group_id, []).append(tuple(target_ids))
        elif alignment_type == "omitted" and (target_ids or spans):
            issues.append(f"sentence alignment {source_id} omitted must not cite target evidence")

    for group_id, targets in many_groups.items():
        if len(targets) < 2 or len(set(targets)) != 1:
            issues.append(f"many_to_one group {group_id} must contain multiple source rows sharing one target unit")

    unaligned = set(_strings(alignment.get("unaligned_target_unit_ids")))
    if not unaligned.issubset(unit_ids):
        issues.append("unaligned_target_unit_ids references unknown target unit")
    if mapped_ids & unaligned:
        issues.append("a target unit cannot be both aligned and unaligned")
    if mapped_ids | unaligned != unit_ids:
        issues.append("every target unit must be aligned or listed as unaligned")
    return issues


def validate_target_analysis(
    analysis: dict[str, Any],
    translation: str,
    expected_units: list[dict[str, Any]] | None = None,
) -> list[str]:
    issues: list[str] = []
    units = _records(analysis.get("target_units"))
    if not units:
        issues.append("target_units must contain at least one unit")
    unit_ids = _unique_ids(units, "unit_id", "target_units", issues)
    for item in units:
        _verbatim(item.get("unit_text"), translation, f"target unit {item.get('unit_id')}", issues)
    if expected_units is not None and units != expected_units:
        issues.append("target_units must exactly match the frozen sentence-alignment units")

    anchors = _records(analysis.get("target_anchors"))
    anchor_ids = _unique_ids(anchors, "target_anchor_id", "target_anchors", issues)
    for item in anchors:
        if item.get("unit_id") not in unit_ids:
            issues.append(f"target anchor {item.get('target_anchor_id')} references unknown unit")
        _verbatim(item.get("target_span"), translation, f"target anchor {item.get('target_anchor_id')}", issues)
        if item.get("anchor_type") not in ANCHOR_TYPES:
            issues.append(f"target anchor {item.get('target_anchor_id')} has unsupported anchor_type")
        _required_field(item, "normalized_value", f"target anchor {item.get('target_anchor_id')}", issues)

    events = _records(analysis.get("target_events"))
    event_ids = _unique_ids(events, "target_event_id", "target_events", issues)
    for item in events:
        for unit_id in _strings(item.get("unit_ids")):
            if unit_id not in unit_ids:
                issues.append(f"target event {item.get('target_event_id')} references unknown unit {unit_id}")
        _verbatim_list(item.get("evidence_spans"), translation, f"target event {item.get('target_event_id')}", issues)
        _required_field(item, "canonical_meaning", f"target event {item.get('target_event_id')}", issues)
        _required_field(item, "predicate", f"target event {item.get('target_event_id')}", issues)
        for argument in _records(item.get("arguments")):
            target_anchor_id = argument.get("target_anchor_id")
            if target_anchor_id and target_anchor_id not in anchor_ids:
                issues.append(f"target event {item.get('target_event_id')} references unknown anchor {target_anchor_id}")
            if argument.get("target_span"):
                _verbatim(argument.get("target_span"), translation, f"target event {item.get('target_event_id')} argument", issues)

    relations = _records(analysis.get("target_relations"))
    _unique_ids(relations, "target_relation_id", "target_relations", issues)
    for item in relations:
        if item.get("relation_type") not in RELATION_TYPES:
            issues.append(f"target relation {item.get('target_relation_id')} has unsupported relation_type")
        if item.get("head_target_event_id") not in event_ids or item.get("dependent_target_event_id") not in event_ids:
            issues.append(f"target relation {item.get('target_relation_id')} references unknown target event")
        _verbatim_list(item.get("target_cues"), translation, f"target relation {item.get('target_relation_id')}", issues, allow_empty=True)
        _required_field(item, "canonical_meaning", f"target relation {item.get('target_relation_id')}", issues)
    return issues


def validate_alignment(
    alignment: dict[str, Any], card: dict[str, Any], translation: str
) -> list[str]:
    issues: list[str] = []
    specs = (
        ("anchor_alignments", "anchor_id", card.get("anchors", [])),
        ("event_alignments", "event_id", card.get("events", [])),
        ("relation_alignments", "relation_id", card.get("relations", [])),
    )
    for key, id_key, source_items in specs:
        rows = _records(alignment.get(key))
        expected = {str(item[id_key]) for item in _records(source_items) if item.get("required", True)}
        actual = [str(item.get(id_key) or "") for item in rows]
        if set(actual) != expected or len(actual) != len(set(actual)):
            issues.append(f"{key} must contain exactly one row for each required {id_key}")
        for item in rows:
            _verbatim_list(item.get("target_spans"), translation, f"{key} {item.get(id_key)}", issues, allow_empty=True)
    return issues


def validate_delivery(delivery: dict[str, Any], translation: str) -> list[str]:
    issues: list[str] = []
    for key in ("fluency_issues", "efficiency_issues"):
        rows = _records(delivery.get(key))
        allowed = FLUENCY_TYPES if key == "fluency_issues" else EFFICIENCY_TYPES
        _unique_ids(rows, "issue_id", key, issues)
        for item in rows:
            _verbatim(item.get("target_span"), translation, f"{key} {item.get('issue_id')}", issues)
            if item.get("issue_type") not in allowed:
                issues.append(f"{key} {item.get('issue_id')} has unsupported issue_type")
            if item.get("severity") not in {"minor", "major", "critical"}:
                issues.append(f"{key} {item.get('issue_id')} has unsupported severity")
    return issues


def _unique_ids(rows: list[dict[str, Any]], key: str, label: str, issues: list[str]) -> set[str]:
    values = [str(item.get(key) or "").strip() for item in rows]
    if any(not value for value in values):
        issues.append(f"{label} contains a missing {key}")
    if len(values) != len(set(values)):
        issues.append(f"{label} contains duplicate {key} values")
    return {value for value in values if value}


def _verbatim(value: Any, text: str, label: str, issues: list[str]) -> None:
    span = _text(value)
    if not span or span not in text:
        issues.append(f"{label} is not a non-empty verbatim span")


def _verbatim_list(value: Any, text: str, label: str, issues: list[str], allow_empty: bool = False) -> None:
    spans = _strings(value)
    if not spans and not allow_empty:
        issues.append(f"{label} has no evidence spans")
    for span in spans:
        _verbatim(span, text, label, issues)


def _importance(item: dict[str, Any], label: str, issues: list[str]) -> None:
    if item.get("importance") not in {1, 2, 3}:
        issues.append(f"{label} importance must be 1, 2, or 3")


def _required_field(item: dict[str, Any], key: str, label: str, issues: list[str]) -> None:
    if not _text(item.get(key)):
        issues.append(f"{label} is missing {key}")


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()
