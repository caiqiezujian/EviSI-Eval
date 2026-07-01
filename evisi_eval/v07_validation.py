"""Validation and deterministic scoring for the v0.7 joint-card protocol."""

from __future__ import annotations

from collections import Counter
from typing import Any

PROTOCOL_VERSION_V07 = "evisi_eval_v0.7"
ANCHOR_TYPES = {"entity", "term", "quantity", "temporal", "scope"}
EVENT_TYPES = {"state", "action", "speech", "judgment"}
RELATION_TYPES = {
    "cause_effect", "condition_consequence", "purpose", "concession", "contrast",
    "temporal_sequence", "temporal_overlap", "conjunction", "progression", "similarity",
    "difference", "degree", "elaboration", "attribution", "exemplification", "conclusion",
}
MATCH_VALUES = {"equivalent", "partial", "contradiction", "missing", "uncertain"}
RELATION_MATCH_VALUES = MATCH_VALUES | {"not_scored"}
DIMENSION_WEIGHTS_V07 = {
    "anchor_fidelity": 35,
    "event_fidelity": 35,
    "relation_fidelity": 10,
    "fluency": 12,
    "si_expression": 8,
}
STATUS_VALUES = {
    "equivalent": 1.0,
    "partial": 0.5,
    "contradiction": 0.0,
    "missing": 0.0,
}
SEVERITY_DEDUCTIONS = {"minor": 2.0, "moderate": 6.0, "major": 15.0, "critical": 35.0}


# ── source validators ──────────────────────────────────────────────

def validate_source_segments(artifact: dict[str, Any], source_text: str) -> list[str]:
    issues = _require_arrays(artifact, ("source_segments",))
    rows = _records(artifact.get("source_segments"))
    _sequential_ids(rows, "seg_id", "S", "source_segments", issues)
    if not rows:
        issues.append("source_segments must contain at least one segment")
    if "".join(str(row.get("source_text") or "") for row in rows) != source_text:
        issues.append("source_segments must concatenate exactly to source_text")
    if any(not str(row.get("source_text") or "").strip() for row in rows):
        issues.append("source_segments cannot contain empty text")
    return issues


def validate_source_anchors(
    artifact: dict[str, Any], segments: list[dict[str, Any]],
) -> list[str]:
    issues = _require_arrays(artifact, ("source_anchors",))
    rows = _records(artifact.get("source_anchors"))
    _seg_prefixed_ids(rows, "anchor_id", "A", "source_anchors", segments, issues)
    segment_text = _unit_text(segments, "seg_id", "source_text")
    for row in rows:
        item_id = str(row.get("anchor_id") or "")
        seg_id = str(row.get("seg_id") or "")
        if seg_id not in segment_text:
            issues.append(f"anchor {item_id} references unknown segment {seg_id}")
        if row.get("type") not in ANCHOR_TYPES:
            issues.append(f"anchor {item_id} has unsupported type: {row.get('type')}")
        if not str(row.get("text") or "").strip():
            issues.append(f"anchor {item_id} text is empty")
        _verbatim(row.get("evidence"), segment_text.get(seg_id, ""),
                  f"anchor {item_id}", issues)
        if row.get("importance") not in {1, 2, 3}:
            issues.append(f"anchor {item_id} importance must be 1, 2, or 3")
    return issues


def validate_source_events(
    artifact: dict[str, Any], segments: list[dict[str, Any]],
) -> list[str]:
    issues = _require_arrays(artifact, ("source_events",))
    rows = _records(artifact.get("source_events"))
    _seg_prefixed_ids(rows, "event_id", "E", "source_events", segments, issues)
    segment_text = _unit_text(segments, "seg_id", "source_text")
    for row in rows:
        item_id = str(row.get("event_id") or "")
        seg_id = str(row.get("seg_id") or "")
        if seg_id not in segment_text:
            issues.append(f"event {item_id} references unknown segment {seg_id}")
        if row.get("type") not in EVENT_TYPES:
            issues.append(f"event {item_id} has unsupported type: {row.get('type')}")
        if not str(row.get("summary") or "").strip():
            issues.append(f"event {item_id} summary is empty")
        _verbatim(row.get("evidence"), segment_text.get(seg_id, ""),
                  f"event {item_id}", issues)
        if row.get("importance") not in {1, 2, 3}:
            issues.append(f"event {item_id} importance must be 1, 2, or 3")
    return issues


def validate_source_relations(
    artifact: dict[str, Any], events: list[dict[str, Any]],
) -> list[str]:
    issues = _require_arrays(artifact, ("source_relations",))
    rows = _records(artifact.get("source_relations"))
    _sequential_ids(rows, "relation_id", "R", "source_relations", issues)
    event_ids = {str(row.get("event_id")) for row in events}
    for row in rows:
        item_id = str(row.get("relation_id") or "")
        if row.get("type") not in RELATION_TYPES:
            issues.append(f"relation {item_id} has unsupported type: {row.get('type')}")
        if not str(row.get("summary") or "").strip():
            issues.append(f"relation {item_id} summary is empty")
        related = _strings(row.get("source_event_ids"))
        if len(related) < 2:
            issues.append(f"relation {item_id} must link at least two events")
        if len(set(related)) != len(related):
            issues.append(f"relation {item_id} has duplicate event IDs")
        if any(eid not in event_ids for eid in related):
            issues.append(f"relation {item_id} references unknown event")
        if not str(row.get("evidence") or "").strip():
            issues.append(f"relation {item_id} evidence is empty")
        if row.get("importance") not in {1, 2, 3}:
            issues.append(f"relation {item_id} importance must be 1, 2, or 3")
    return issues


# ── reference validators ───────────────────────────────────────────

def validate_reference_alignment(
    artifact: dict[str, Any], source_segments: list[dict[str, Any]],
    reference_translation: str,
) -> list[str]:
    issues = _require_arrays(artifact, ("reference_segments",))
    rows = _records(artifact.get("reference_segments"))
    source_ids = [str(row.get("seg_id")) for row in source_segments]
    ref_ids = [str(row.get("seg_id") or "") for row in rows]
    if ref_ids != source_ids:
        issues.append(
            f"reference_segments seg_ids must match source_segments exactly: "
            f"expected {source_ids}, got {ref_ids}"
        )
    if "".join(str(row.get("reference_text") or "") for row in rows) != reference_translation:
        issues.append("reference_segments must concatenate exactly to reference_translation")
    if any(not str(row.get("reference_text") or "").strip() for row in rows):
        issues.append("reference_segments cannot contain empty text")
    return issues


def validate_reference_anchors(
    artifact: dict[str, Any], source_anchors: list[dict[str, Any]],
    reference_segments: list[dict[str, Any]],
) -> list[str]:
    issues = _require_arrays(artifact, ("reference_anchors",))
    rows = _records(artifact.get("reference_anchors"))
    issues.extend(_positional_match(
        rows, source_anchors, "anchor_id", "reference_anchors",
    ))
    segment_text = _unit_text(reference_segments, "seg_id", "reference_text")
    for i, row in enumerate(rows):
        source = source_anchors[i] if i < len(source_anchors) else {}
        expected_seg = str(source.get("seg_id") or "")
        actual_seg = str(row.get("seg_id") or "")
        if expected_seg and actual_seg != expected_seg:
            issues.append(
                f"reference_anchors[{i}] seg_id mismatch: expected {expected_seg}, got {actual_seg}"
            )
        evidence = str(row.get("evidence") or "")
        if evidence:
            _verbatim(evidence, segment_text.get(actual_seg, ""),
                      f"reference_anchors[{i}]", issues)
        text_val = str(row.get("text") or "")
        if not text_val and evidence:
            issues.append(f"reference_anchors[{i}] has evidence but empty text")
    return issues


def validate_reference_events(
    artifact: dict[str, Any], source_events: list[dict[str, Any]],
    reference_segments: list[dict[str, Any]],
) -> list[str]:
    issues = _require_arrays(artifact, ("reference_events",))
    rows = _records(artifact.get("reference_events"))
    issues.extend(_positional_match(
        rows, source_events, "event_id", "reference_events",
    ))
    segment_text = _unit_text(reference_segments, "seg_id", "reference_text")
    for i, row in enumerate(rows):
        source = source_events[i] if i < len(source_events) else {}
        expected_seg = str(source.get("seg_id") or "")
        actual_seg = str(row.get("seg_id") or "")
        if expected_seg and actual_seg != expected_seg:
            issues.append(
                f"reference_events[{i}] seg_id mismatch: expected {expected_seg}, got {actual_seg}"
            )
        evidence = str(row.get("evidence") or "")
        if evidence:
            _verbatim(evidence, segment_text.get(actual_seg, ""),
                      f"reference_events[{i}]", issues)
            if not str(row.get("summary") or "").strip():
                issues.append(f"reference_events[{i}] has evidence but empty summary")
    return issues


def validate_reference_relations(
    artifact: dict[str, Any], source_relations: list[dict[str, Any]],
) -> list[str]:
    issues = _require_arrays(artifact, ("reference_relations",))
    rows = _records(artifact.get("reference_relations"))
    issues.extend(_positional_match(
        rows, source_relations, "relation_id", "reference_relations",
    ))
    for i, row in enumerate(rows):
        if not isinstance(row.get("preserved"), bool):
            issues.append(f"reference_relations[{i}] preserved must be boolean")
        if not str(row.get("summary") or "").strip():
            issues.append(f"reference_relations[{i}] summary is empty")
    return issues


# ── SI validators ───────────────────────────────────────────────────

def validate_si_alignment(
    artifact: dict[str, Any], source_segments: list[dict[str, Any]],
    si_translation: str,
) -> list[str]:
    issues = _require_arrays(artifact, ("si_segments",))
    rows = _records(artifact.get("si_segments"))
    source_ids = [str(row.get("seg_id")) for row in source_segments]
    si_ids = [str(row.get("seg_id") or "") for row in rows]
    if si_ids != source_ids:
        issues.append(
            f"si_segments seg_ids must match source_segments exactly: "
            f"expected {source_ids}, got {si_ids}"
        )
    if "".join(str(row.get("si_text") or "") for row in rows) != si_translation:
        issues.append("si_segments must concatenate exactly to si_translation")
    if any(not str(row.get("si_text") or "").strip() for row in rows):
        issues.append("si_segments cannot contain empty text")
    return issues


def validate_si_anchor_matches(
    artifact: dict[str, Any], joint_anchors: list[dict[str, Any]],
    si_segments: list[dict[str, Any]],
) -> list[str]:
    issues = _require_arrays(artifact, ("anchor_matches",))
    rows = _records(artifact.get("anchor_matches"))
    issues.extend(_positional_match(
        rows, joint_anchors, "anchor_id", "anchor_matches",
    ))
    segment_text = _unit_text(si_segments, "seg_id", "si_text")
    for i, row in enumerate(rows):
        item_id = str(row.get("anchor_id") or "")
        if row.get("match") not in MATCH_VALUES:
            issues.append(f"anchor_match {item_id} has unsupported match: {row.get('match')}")
        evidence = str(row.get("si_evidence") or "")
        if evidence:
            joint = joint_anchors[i] if i < len(joint_anchors) else {}
            seg_id = str(joint.get("seg_id") or "")
            if seg_id:
                _verbatim(evidence, segment_text.get(seg_id, ""),
                          f"anchor_match {item_id}", issues)
        if not str(row.get("brief") or "").strip():
            issues.append(f"anchor_match {item_id} brief is empty")
    return issues


def validate_si_event_matches(
    artifact: dict[str, Any], joint_events: list[dict[str, Any]],
    si_segments: list[dict[str, Any]],
) -> list[str]:
    issues = _require_arrays(artifact, ("event_matches",))
    rows = _records(artifact.get("event_matches"))
    issues.extend(_positional_match(
        rows, joint_events, "event_id", "event_matches",
    ))
    segment_text = _unit_text(si_segments, "seg_id", "si_text")
    for i, row in enumerate(rows):
        item_id = str(row.get("event_id") or "")
        if row.get("match") not in MATCH_VALUES:
            issues.append(f"event_match {item_id} has unsupported match: {row.get('match')}")
        evidence = str(row.get("si_evidence") or "")
        if evidence:
            joint = joint_events[i] if i < len(joint_events) else {}
            seg_id = str(joint.get("seg_id") or "")
            if seg_id:
                _verbatim(evidence, segment_text.get(seg_id, ""),
                          f"event_match {item_id}", issues)
        if not str(row.get("brief") or "").strip():
            issues.append(f"event_match {item_id} brief is empty")
    return issues


def validate_si_relation_matches(
    artifact: dict[str, Any], joint_relations: list[dict[str, Any]],
    si_event_matches: list[dict[str, Any]] | None = None,
) -> list[str]:
    issues = _require_arrays(artifact, ("relation_matches",))
    rows = _records(artifact.get("relation_matches"))
    issues.extend(_positional_match(
        rows, joint_relations, "relation_id", "relation_matches",
    ))
    event_status: dict[str, str] = {}
    if si_event_matches is not None:
        event_status = {
            str(row.get("event_id")): str(row.get("match") or "uncertain")
            for row in si_event_matches
        }
    for i, row in enumerate(rows):
        item_id = str(row.get("relation_id") or "")
        match_val = row.get("match")
        if match_val not in RELATION_MATCH_VALUES:
            issues.append(f"relation_match {item_id} has unsupported match: {match_val}")
        if not str(row.get("brief") or "").strip():
            issues.append(f"relation_match {item_id} brief is empty")
        if match_val == "not_scored":
            joint = joint_relations[i] if i < len(joint_relations) else {}
            endpoint_ids = _strings(joint.get("source_event_ids"))
            endpoint_statuses = [event_status.get(eid, "uncertain") for eid in endpoint_ids]
            if not endpoint_statuses or any(
                s not in ("missing", "contradiction") for s in endpoint_statuses
            ):
                issues.append(
                    f"relation_match {item_id} not_scored but not all endpoints are "
                    f"missing/contradiction: {dict(zip(endpoint_ids, endpoint_statuses))}"
                )
    return issues


# ── joint card assembly validation ──────────────────────────────────

def validate_joint_card_assembly(
    source_segments: list[dict[str, Any]],
    source_anchors: list[dict[str, Any]],
    source_events: list[dict[str, Any]],
    source_relations: list[dict[str, Any]],
    reference_segments: list[dict[str, Any]],
    reference_anchors: list[dict[str, Any]],
    reference_events: list[dict[str, Any]],
    reference_relations: list[dict[str, Any]],
) -> list[str]:
    """Validate that source and reference sides can be zipped into a joint card."""
    issues: list[str] = []
    if len(reference_anchors) != len(source_anchors):
        issues.append(
            f"reference_anchors count ({len(reference_anchors)}) != "
            f"source_anchors count ({len(source_anchors)})"
        )
    if len(reference_events) != len(source_events):
        issues.append(
            f"reference_events count ({len(reference_events)}) != "
            f"source_events count ({len(source_events)})"
        )
    if len(reference_relations) != len(source_relations):
        issues.append(
            f"reference_relations count ({len(reference_relations)}) != "
            f"source_relations count ({len(source_relations)})"
        )
    # Verify positional ID match
    for i, (src, ref) in enumerate(zip(source_anchors, reference_anchors)):
        if str(ref.get("anchor_id") or "") != str(src.get("anchor_id") or ""):
            issues.append(
                f"reference_anchors[{i}] anchor_id mismatch: "
                f"{ref.get('anchor_id')} != {src.get('anchor_id')}"
            )
    for i, (src, ref) in enumerate(zip(source_events, reference_events)):
        if str(ref.get("event_id") or "") != str(src.get("event_id") or ""):
            issues.append(
                f"reference_events[{i}] event_id mismatch: "
                f"{ref.get('event_id')} != {src.get('event_id')}"
            )
    for i, (src, ref) in enumerate(zip(source_relations, reference_relations)):
        if str(ref.get("relation_id") or "") != str(src.get("relation_id") or ""):
            issues.append(
                f"reference_relations[{i}] relation_id mismatch: "
                f"{ref.get('relation_id')} != {src.get('relation_id')}"
            )
    return issues


# ── scoring ─────────────────────────────────────────────────────────

def calculate_v07_scores(
    joint_anchors: list[dict[str, Any]],
    joint_events: list[dict[str, Any]],
    joint_relations: list[dict[str, Any]],
    anchor_matches: list[dict[str, Any]],
    event_matches: list[dict[str, Any]],
    relation_matches: list[dict[str, Any]],
    fluency_issues: list[dict[str, Any]],
    expression_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    """Deterministic scoring from SI match results and delivery issues."""
    anchor_score, anchor_diag = _match_dimension(
        joint_anchors, anchor_matches, "anchor_id",
    )
    event_score, event_diag = _match_dimension(
        joint_events, event_matches, "event_id",
    )
    relation_score, relation_diag = _match_dimension(
        joint_relations, relation_matches, "relation_id",
        skip_statuses={"not_scored"},
    )
    fluency_score = _delivery_score(fluency_issues)
    expression_score = _delivery_score(expression_issues)

    scores = {
        "anchor_fidelity": anchor_score,
        "event_fidelity": event_score,
        "relation_fidelity": relation_score,
        "fluency": fluency_score,
        "si_expression": expression_score,
    }
    diagnostics = {
        "anchor_fidelity": anchor_diag,
        "event_fidelity": event_diag,
        "relation_fidelity": relation_diag,
        "fluency": {"applicable": True, "issue_count": len(fluency_issues)},
        "si_expression": {"applicable": True, "issue_count": len(expression_issues)},
    }

    active = [
        key for key, value in scores.items()
        if value is not None and diagnostics[key].get("applicable", True)
    ]
    active_weight = sum(DIMENSION_WEIGHTS_V07[key] for key in active)

    no_decisions = any(
        diagnostics[key].get("decision_status") == "no_decisions"
        for key in ("anchor_fidelity", "event_fidelity", "relation_fidelity")
        if diagnostics[key].get("applicable")
    )
    final_score = None if no_decisions else round(
        sum(float(scores[key]) * DIMENSION_WEIGHTS_V07[key] for key in active) / active_weight,
        2,
    )
    uncertain = sum(
        int(diagnostics[key].get("uncertain_items", 0))
        for key in ("anchor_fidelity", "event_fidelity", "relation_fidelity")
    )

    if no_decisions:
        status = "provisional_no_decisions"
    elif uncertain > 0:
        status = "provisional_review_required"
    else:
        status = "final"

    return {
        "dimension_scores": scores,
        "dimension_weights": DIMENSION_WEIGHTS_V07,
        "score_diagnostics": diagnostics,
        "final_score": final_score,
        "score_status": status,
    }


def _match_dimension(
    joint_items: list[dict[str, Any]],
    matches: list[dict[str, Any]],
    id_key: str,
    skip_statuses: set[str] | None = None,
) -> tuple[float | None, dict[str, Any]]:
    matches_by_id = {str(row.get(id_key)): row for row in matches}
    if not joint_items:
        return 100.0, {
            "applicable": False, "decision_status": "not_applicable",
            "total_items": 0, "decided_items": 0, "uncertain_items": 0,
            "decided_weight": 0.0, "earned_weight": 0.0, "item_decisions": [],
        }
    earned = 0.0
    decided_weight = 0.0
    uncertain = 0
    blocked = 0
    item_decisions: list[dict[str, Any]] = []

    for item in joint_items:
        item_id = str(item.get(id_key) or "")
        match_row = matches_by_id.get(item_id, {})
        status = str(match_row.get("match") or "uncertain")
        weight = float(item.get("importance", 1))

        decision: dict[str, Any] = {
            id_key: item_id,
            "importance": weight,
            "match": status,
            "score_value": None,
            "weighted_contribution": None,
        }
        # Include source/reference context for diagnostics
        if id_key == "anchor_id":
            decision["type"] = item.get("type")
            decision["source_text"] = item.get("source_text")
            decision["reference_text"] = item.get("reference_text")
            decision["si_text"] = match_row.get("si_text")
        elif id_key == "event_id":
            decision["type"] = item.get("type")
            decision["source_summary"] = item.get("source_summary")
            decision["reference_summary"] = item.get("reference_summary")
            decision["si_summary"] = match_row.get("si_summary")

        if status == "uncertain":
            uncertain += 1
            item_decisions.append(decision)
            continue
        if status in (skip_statuses or set()):
            blocked += 1
            item_decisions.append(decision)
            continue

        value = STATUS_VALUES.get(status, 0.0)
        contribution = weight * value
        decision["score_value"] = value
        decision["weighted_contribution"] = contribution
        item_decisions.append(decision)
        earned += contribution
        decided_weight += weight

    if decided_weight == 0:
        if blocked == len(joint_items) and uncertain == 0:
            return None, {
                "applicable": False, "decision_status": "blocked_by_dependency",
                "total_items": len(joint_items), "decided_items": 0,
                "uncertain_items": 0, "blocked_items": blocked,
                "decided_weight": 0.0, "earned_weight": 0.0,
                "item_decisions": item_decisions,
            }
        return None, {
            "applicable": True, "decision_status": "no_decisions",
            "total_items": len(joint_items), "decided_items": 0,
            "uncertain_items": uncertain, "blocked_items": blocked,
            "decided_weight": 0.0, "earned_weight": 0.0,
            "item_decisions": item_decisions,
        }

    status_label = "complete" if uncertain == 0 else "partial_decisions"
    return round(100 * earned / decided_weight, 2), {
        "applicable": True, "decision_status": status_label,
        "total_items": len(joint_items),
        "decided_items": len(joint_items) - uncertain - blocked,
        "uncertain_items": uncertain, "blocked_items": blocked,
        "decided_weight": decided_weight, "earned_weight": earned,
        "item_decisions": item_decisions,
    }


def _delivery_score(issues: list[dict[str, Any]]) -> float:
    deduction = sum(
        SEVERITY_DEDUCTIONS.get(str(row.get("severity")), 0) for row in issues
    )
    return round(max(0.0, 100.0 - deduction), 2)


# ── helpers ─────────────────────────────────────────────────────────

def _require_arrays(artifact: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [
        f"{field} must be an array"
        for field in fields if not isinstance(artifact.get(field), list)
    ]


def _sequential_ids(
    rows: list[dict[str, Any]], key: str, prefix: str, label: str, issues: list[str],
) -> None:
    expected = [f"{prefix}{index}" for index in range(1, len(rows) + 1)]
    actual = [str(row.get(key) or "") for row in rows]
    if actual != expected:
        issues.append(f"{label} IDs must be sequential: expected {expected}, got {actual}")


def _seg_prefixed_ids(
    rows: list[dict[str, Any]], key: str, suffix_prefix: str, label: str,
    segments: list[dict[str, Any]], issues: list[str],
) -> None:
    """Validate segment-prefixed IDs like S1_A1, S1_E1.

    Each segment's items must have sequential numbering within that segment,
    and all items must belong to a known segment.
    """
    seg_ids = {str(s.get("seg_id")) for s in segments}
    by_segment: dict[str, list[int]] = {}
    for row in rows:
        item_id = str(row.get(key) or "")
        seg_id = str(row.get("seg_id") or "")
        if seg_id not in seg_ids:
            issues.append(f"{label} {item_id} references unknown segment {seg_id}")
            continue
        # Parse the numeric suffix: S1_A1 → extract 1 from A1
        parts = item_id.split("_")
        if len(parts) >= 2:
            suffix = parts[-1]  # e.g., "A1"
            prefix = suffix_prefix
            if suffix.startswith(prefix):
                try:
                    num = int(suffix[len(prefix):])
                    by_segment.setdefault(seg_id, []).append(num)
                except ValueError:
                    issues.append(f"{label} {item_id} has malformed suffix")
            else:
                issues.append(
                    f"{label} {item_id} suffix must start with {prefix}, got {suffix}"
                )
    for seg_id, nums in by_segment.items():
        expected = list(range(1, len(nums) + 1))
        if sorted(nums) != expected:
            issues.append(
                f"{label} in {seg_id} must be sequential: "
                f"expected {expected}, got {sorted(nums)}"
            )


def _positional_match(
    rows: list[dict[str, Any]], source_items: list[dict[str, Any]],
    id_key: str, label: str,
) -> list[str]:
    """Verify rows have same count and positional IDs as source items."""
    issues: list[str] = []
    if len(rows) != len(source_items):
        issues.append(
            f"{label} count ({len(rows)}) != source count ({len(source_items)})"
        )
        return issues
    for i, (row, source) in enumerate(zip(rows, source_items)):
        actual = str(row.get(id_key) or "")
        expected = str(source.get(id_key) or "")
        if actual != expected:
            issues.append(
                f"{label}[{i}] {id_key} mismatch: expected {expected}, got {actual}"
            )
    return issues


def _verbatim(value: Any, text: str, label: str, issues: list[str]) -> None:
    span = str(value or "")
    if not span:
        return  # empty is ok for missing items
    if span not in text:
        issues.append(f"{label} evidence '{span[:80]}' not found verbatim in source text")


def _unit_text(rows: list[dict[str, Any]], id_key: str, text_key: str) -> dict[str, str]:
    return {str(row.get(id_key)): str(row.get(text_key) or "") for row in rows}


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []
