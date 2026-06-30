"""Validation and deterministic scoring for the v0.6 source-conditioned protocol."""

from __future__ import annotations

from collections import Counter
from typing import Any


PROTOCOL_VERSION_V06 = "evisi_eval_v0.6"
ANCHOR_TYPES = {"A-ENT", "A-QNT", "A-TMP", "A-TERM", "A-SCOPE"}
EVENT_TYPES = {"E-ACT", "E-STATE", "E-CHANGE", "E-JUDG", "E-REL", "E-SPEECH", "E-MODAL"}
RELATION_TYPES = {
    "cause_effect", "condition_consequence", "purpose", "concession", "contrast",
    "temporal_sequence", "temporal_overlap", "conjunction", "progression", "similarity",
    "difference", "degree", "elaboration", "attribution", "exemplification", "exception",
    "conclusion",
}
RELATION_BASES = {"explicit_cue", "strong_semantic_entailment"}
ALIGNMENT_STATUSES = {"aligned", "source_omitted", "target_addition", "uncertain"}
MAPPING_STATUSES = {"equivalent", "partial", "contradiction", "missing", "uncertain"}
RELATION_MAPPING_STATUSES = MAPPING_STATUSES | {"not_scored"}
COMPONENT_STATUSES = {"preserved", "omitted", "contradicted", "uncertain"}
HARD_REQUIREMENT_TYPES = {
    "exact_target_form", "exact_value_unit", "required_event_semantics",
}
DIMENSION_WEIGHTS_V06 = {
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
SEVERITY_DEDUCTIONS_V06 = {"minor": 2.0, "moderate": 6.0, "major": 15.0, "critical": 35.0}


def validate_source_segments(artifact: dict[str, Any], source_text: str) -> list[str]:
    issues = _require_arrays(artifact, ("source_segments",))
    rows = _records(artifact.get("source_segments"))
    _sequential_ids(rows, "segment_id", "G", "source_segments", issues)
    if not rows:
        issues.append("source_segments must contain at least one segment")
    if "".join(str(row.get("source_segment") or "") for row in rows) != source_text:
        issues.append("source_segments must concatenate exactly to source_text")
    if any(not str(row.get("source_segment") or "") for row in rows):
        issues.append("source_segments cannot contain empty text")
    return issues


def validate_source_anchors(
    artifact: dict[str, Any], segments: list[dict[str, Any]]
) -> list[str]:
    issues = _require_arrays(artifact, ("source_anchors",))
    rows = _records(artifact.get("source_anchors"))
    _sequential_ids(rows, "source_anchor_id", "SA", "source_anchors", issues)
    segment_text = _unit_text(segments, "segment_id", "source_segment")
    for row in rows:
        item_id = str(row.get("source_anchor_id") or "")
        segment_id = str(row.get("segment_id") or "")
        if segment_id not in segment_text:
            issues.append(f"anchor {item_id} references unknown segment")
        if row.get("anchor_type") not in ANCHOR_TYPES:
            issues.append(f"anchor {item_id} has unsupported anchor_type")
        _verbatim(row.get("evidence_span"), segment_text.get(segment_id, ""), f"anchor {item_id}", issues)
        if not str(row.get("anchor_text") or "").strip() or not str(row.get("normalized_value") or "").strip():
            issues.append(f"anchor {item_id} is missing semantic fields")
        if row.get("importance") not in {1, 2, 3}:
            issues.append(f"anchor {item_id} importance must be 1, 2, or 3")
        components = row.get("components")
        if not isinstance(components, dict) or not components:
            issues.append(f"anchor {item_id} components must be a non-empty object")
        elif any(not str(key).strip() for key in components):
            issues.append(f"anchor {item_id} component names must be non-empty")
        elif any(
            value is None or isinstance(value, (dict, list)) or not str(value).strip()
            for value in components.values()
        ):
            issues.append(f"anchor {item_id} components must contain atomic non-empty values")
    return issues


def validate_source_events(
    artifact: dict[str, Any], segments: list[dict[str, Any]], anchors: list[dict[str, Any]]
) -> list[str]:
    issues = _require_arrays(artifact, ("source_events",))
    rows = _records(artifact.get("source_events"))
    _sequential_ids(rows, "source_event_id", "SE", "source_events", issues)
    segment_text = _unit_text(segments, "segment_id", "source_segment")
    anchor_ids = {str(row.get("source_anchor_id")) for row in anchors}
    for row in rows:
        item_id = str(row.get("source_event_id") or "")
        segment_id = str(row.get("segment_id") or "")
        text = segment_text.get(segment_id, "")
        if segment_id not in segment_text:
            issues.append(f"event {item_id} references unknown segment")
        if row.get("event_type") not in EVENT_TYPES:
            issues.append(f"event {item_id} has unsupported event_type")
        evidence = _strings(row.get("evidence_spans"))
        if not evidence or any(span not in text for span in evidence):
            issues.append(f"event {item_id} has invalid evidence_spans")
        _verbatim(row.get("predicate_span"), text, f"event {item_id} predicate", issues)
        if not str(row.get("core_predicate") or "").strip() or not str(row.get("canonical_proposition") or "").strip():
            issues.append(f"event {item_id} is missing predicate/proposition")
        if not isinstance(row.get("arguments"), list):
            issues.append(f"event {item_id} arguments must be an array")
        arguments = _records(row.get("arguments"))
        argument_keys: list[tuple[str, str]] = []
        for argument in arguments:
            role = str(argument.get("role") or "").strip()
            span = str(argument.get("surface_span") or "")
            if not role:
                issues.append(f"event {item_id} has an argument without a role")
            if span and span not in text:
                issues.append(f"event {item_id} has non-verbatim argument span")
            if not isinstance(argument.get("source_anchor_ids"), list):
                issues.append(f"event {item_id} argument source_anchor_ids must be an array")
            linked_anchors = _strings(argument.get("source_anchor_ids"))
            if len(linked_anchors) != len(set(linked_anchors)):
                issues.append(f"event {item_id} argument contains duplicate anchor links")
            if any(anchor_id not in anchor_ids for anchor_id in linked_anchors):
                issues.append(f"event {item_id} references unknown anchor")
            argument_keys.append((role, span))
        if len(argument_keys) != len(set(argument_keys)):
            issues.append(f"event {item_id} contains duplicate arguments")
        operators = row.get("operators")
        if not isinstance(operators, dict):
            issues.append(f"event {item_id} operators must be an object")
        elif set(operators) != {"negation", "modality", "direction", "polarity", "stance"}:
            issues.append(f"event {item_id} operators must use the canonical five fields")
        if row.get("importance") not in {1, 2, 3}:
            issues.append(f"event {item_id} importance must be 1, 2, or 3")
    return issues


def validate_source_relations(
    artifact: dict[str, Any], segments: list[dict[str, Any]], events: list[dict[str, Any]]
) -> list[str]:
    issues = _require_arrays(artifact, ("source_relations",))
    rows = _records(artifact.get("source_relations"))
    _sequential_ids(rows, "source_relation_id", "SR", "source_relations", issues)
    segment_text = _unit_text(segments, "segment_id", "source_segment")
    event_ids = {str(row.get("source_event_id")) for row in events}
    event_segment = {
        str(row.get("source_event_id")): str(row.get("segment_id")) for row in events
    }
    segment_order = {key: index for index, key in enumerate(segment_text)}
    for row in rows:
        item_id = str(row.get("source_relation_id") or "")
        selected = _strings(row.get("segment_ids"))
        indexes = [segment_order[item] for item in selected if item in segment_order]
        if not selected or len(indexes) != len(selected):
            issues.append(f"relation {item_id} references invalid segments")
        elif indexes != sorted(set(indexes)):
            issues.append(f"relation {item_id} segment_ids must be unique and ordered")
        related = _strings(row.get("related_source_event_ids"))
        if len(related) < 2 or len(set(related)) != len(related):
            issues.append(f"relation {item_id} must link at least two distinct events")
        if any(event_id not in event_ids for event_id in related):
            issues.append(f"relation {item_id} references unknown event")
        if any(event_segment.get(event_id) not in set(selected) for event_id in related):
            issues.append(f"relation {item_id} links event outside selected segments")
        if row.get("relation_type") not in RELATION_TYPES:
            issues.append(f"relation {item_id} has unsupported relation_type")
        basis = row.get("relation_basis")
        cue = str(row.get("relation_cue") or "")
        confidence = row.get("confidence")
        texts = [segment_text.get(segment_id, "") for segment_id in selected]
        if basis not in RELATION_BASES:
            issues.append(f"relation {item_id} has unsupported relation_basis")
        if not _is_number(confidence) or not 0 <= float(confidence) <= 1:
            issues.append(f"relation {item_id} confidence must be between 0 and 1")
        elif basis == "strong_semantic_entailment" and float(confidence) < 0.85:
            issues.append(f"implicit relation {item_id} confidence must be at least 0.85")
        if basis == "explicit_cue" and (not cue or not any(cue in text for text in texts)):
            issues.append(f"explicit relation {item_id} needs a verbatim relation_cue")
        if basis == "strong_semantic_entailment" and cue:
            issues.append(f"implicit relation {item_id} must use an empty relation_cue")
        evidence = _strings(row.get("evidence_spans"))
        if not evidence or any(not any(span in text for text in texts) for span in evidence):
            issues.append(f"relation {item_id} has invalid evidence_spans")
        if row.get("importance") not in {1, 2, 3}:
            issues.append(f"relation {item_id} importance must be 1, 2, or 3")
    return issues


def validate_target_alignment(
    artifact: dict[str, Any], segments: list[dict[str, Any]], translation: str
) -> list[str]:
    issues = _require_arrays(artifact, ("target_units",))
    rows = _records(artifact.get("target_units"))
    _sequential_ids(rows, "target_unit_id", "T", "target_units", issues)
    if not rows:
        issues.append("target_units must contain at least one unit")
    if "".join(str(row.get("target_text") or "") for row in rows) != translation:
        issues.append("target_units must concatenate exactly to target translation")
    source_ids = {str(row.get("segment_id")) for row in segments}
    occurrences: list[str] = []
    for row in rows:
        unit_id = str(row.get("target_unit_id") or "")
        linked = _strings(row.get("source_segment_ids"))
        if any(segment_id not in source_ids for segment_id in linked):
            issues.append(f"target unit {unit_id} references unknown source segment")
        occurrences.extend(linked)
        status = row.get("alignment_status")
        target_text = str(row.get("target_text") or "")
        if status not in ALIGNMENT_STATUSES:
            issues.append(f"target unit {unit_id} has unsupported alignment_status")
        elif status == "aligned" and (not linked or not target_text):
            issues.append(f"aligned target unit {unit_id} needs source and target")
        elif status == "source_omitted" and (not linked or target_text):
            issues.append(f"source_omitted target unit {unit_id} needs source IDs and empty text")
        elif status == "target_addition" and (linked or not target_text):
            issues.append(f"target_addition target unit {unit_id} needs target text only")
        if not str(row.get("reason") or "").strip():
            issues.append(f"target unit {unit_id} needs a reason")
    counts = Counter(occurrences)
    if any(counts.get(segment_id, 0) == 0 for segment_id in source_ids):
        issues.append("every source segment must be represented or marked omitted")
    return issues


def validate_anchor_projections(
    artifact: dict[str, Any], source_anchors: list[dict[str, Any]], target_units: list[dict[str, Any]],
    *, si_mode: bool,
) -> list[str]:
    issues = _validate_projections(
        artifact, "anchor_projections", "AP", "source_anchor_id", source_anchors,
        target_units, MAPPING_STATUSES, si_mode=si_mode, relation_mode=False,
    )
    source_by_id = {str(row.get("source_anchor_id")): row for row in source_anchors}
    target_text = _unit_text(target_units, "target_unit_id", "target_text")
    for row in _records(artifact.get("anchor_projections")):
        projection_id = str(row.get("projection_id") or "")
        source = source_by_id.get(str(row.get("source_anchor_id") or ""), {})
        expected_components = set(
            source.get("components", {}) if isinstance(source.get("components"), dict) else {}
        )
        component_rows = _records(row.get("component_results"))
        component_names = [str(item.get("component") or "") for item in component_rows]
        if Counter(component_names) != Counter(expected_components):
            issues.append(f"projection {projection_id} must cover every source component exactly once")
        selected = _strings(row.get("target_unit_ids"))
        statuses = []
        for component in component_rows:
            component_name = str(component.get("component") or "")
            status = component.get("status")
            statuses.append(status)
            if status not in COMPONENT_STATUSES:
                issues.append(f"projection {projection_id} has invalid component status")
            span = str(component.get("target_span") or "")
            if span and not any(span in target_text.get(unit_id, "") for unit_id in selected):
                issues.append(f"projection {projection_id} has non-verbatim component span")
            if component_name in expected_components and not _same_component_value(
                component.get("source_value"), source.get("components", {}).get(component_name)
            ):
                issues.append(f"projection {projection_id} changed source component value")
            target_value = component.get("target_value")
            if status == "omitted" and (target_value is not None or span):
                issues.append(f"projection {projection_id} omitted component cannot cite a value")
            if status in {"preserved", "contradicted"} and (target_value is None or not span):
                issues.append(
                    f"projection {projection_id} decided component needs target value and span"
                )
        _validate_aggregate_status(projection_id, row.get("mapping_status"), statuses, issues)
    return issues


def validate_event_projections(
    artifact: dict[str, Any], source_events: list[dict[str, Any]], target_units: list[dict[str, Any]],
    *, si_mode: bool,
) -> list[str]:
    issues = _validate_projections(
        artifact, "event_projections", "EP", "source_event_id", source_events,
        target_units, MAPPING_STATUSES, si_mode=si_mode, relation_mode=False,
    )
    for row in _records(artifact.get("event_projections")):
        projection_id = str(row.get("projection_id") or "")
        selected = _strings(row.get("target_unit_ids"))
        target_text = _unit_text(target_units, "target_unit_id", "target_text")
        component_statuses = []
        for key in ("predicate_status", "argument_status", "operator_status"):
            component_statuses.append(row.get(key))
            if row.get(key) not in COMPONENT_STATUSES:
                issues.append(f"projection {projection_id} has unsupported {key}")
        _validate_aggregate_status(
            projection_id, row.get("mapping_status"), component_statuses, issues
        )
        structure = row.get("target_event_structure")
        if not isinstance(structure, dict):
            issues.append(f"projection {projection_id} target_event_structure must be an object")
            continue
        if row.get("mapping_status") != "missing":
            required_structure = {
                "core_predicate", "predicate_span", "arguments", "operators",
                "canonical_proposition",
            }
            if set(structure) != required_structure:
                issues.append(
                    f"projection {projection_id} target_event_structure must use canonical fields"
                )
            if not str(structure.get("core_predicate") or "").strip() or not str(
                structure.get("canonical_proposition") or ""
            ).strip():
                issues.append(f"projection {projection_id} needs target event semantics")
            predicate_span = str(structure.get("predicate_span") or "")
            if row.get("predicate_status") in {"preserved", "contradicted"}:
                if not predicate_span or not any(
                    predicate_span in target_text.get(unit_id, "") for unit_id in selected
                ):
                    issues.append(f"projection {projection_id} needs verbatim predicate evidence")
            arguments = structure.get("arguments")
            if not isinstance(arguments, list):
                issues.append(f"projection {projection_id} target arguments must be an array")
            else:
                for argument in _records(arguments):
                    span = str(argument.get("surface_span") or "")
                    if span and not any(
                        span in target_text.get(unit_id, "") for unit_id in selected
                    ):
                        issues.append(
                            f"projection {projection_id} has non-verbatim target argument"
                        )
            operators = structure.get("operators")
            if not isinstance(operators, dict) or set(operators) != {
                "negation", "modality", "direction", "polarity", "stance",
            }:
                issues.append(f"projection {projection_id} target operators are incomplete")
    return issues


def validate_relation_projections(
    artifact: dict[str, Any], source_relations: list[dict[str, Any]], target_units: list[dict[str, Any]],
    *, si_mode: bool, event_projections: list[dict[str, Any]] | None = None,
) -> list[str]:
    issues = _validate_projections(
        artifact, "relation_projections", "RP", "source_relation_id", source_relations,
        target_units, RELATION_MAPPING_STATUSES, si_mode=si_mode, relation_mode=True,
    )
    source_by_id = {str(row.get("source_relation_id")): row for row in source_relations}
    event_status = {
        str(row.get("source_event_id")): str(row.get("mapping_status") or "uncertain")
        for row in (event_projections or [])
    }
    for row in _records(artifact.get("relation_projections")):
        projection_id = str(row.get("projection_id") or "")
        dependency = row.get("dependency_status")
        if dependency not in {"endpoints_available", "blocked_by_event"}:
            issues.append(f"projection {projection_id} has unsupported dependency_status")
        if dependency == "blocked_by_event" and row.get("mapping_status") != "not_scored":
            issues.append(f"projection {projection_id} blocked relation must be not_scored")
        if dependency == "endpoints_available" and row.get("mapping_status") == "not_scored":
            issues.append(f"projection {projection_id} available relation cannot be not_scored")
        if event_projections is not None:
            source_relation = source_by_id.get(str(row.get("source_relation_id") or ""), {})
            endpoint_statuses = [
                event_status.get(event_id, "uncertain")
                for event_id in _strings(source_relation.get("related_source_event_ids"))
            ]
            should_block = any(status not in {"equivalent", "partial"} for status in endpoint_statuses)
            if should_block and dependency != "blocked_by_event":
                issues.append(f"projection {projection_id} must be blocked by unavailable event")
            if not should_block and dependency != "endpoints_available":
                issues.append(f"projection {projection_id} has available event endpoints")
    return issues


def validate_requirement_inheritance(
    artifact: dict[str, Any], reference_card: dict[str, Any], list_key: str,
    source_id_key: str,
) -> list[str]:
    reference = {
        str(row.get(source_id_key)): row.get("hard_requirement")
        for row in _records(reference_card.get(list_key))
    }
    issues = []
    for row in _records(artifact.get(list_key)):
        source_id = str(row.get(source_id_key) or "")
        if row.get("hard_requirement") != reference.get(source_id):
            issues.append(f"projection {row.get('projection_id')} changed frozen hard requirement")
    return issues


def calculate_v06_scores(
    source_card: dict[str, Any], si_card: dict[str, Any],
    fluency_issues: list[dict[str, Any]], expression_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    anchor_score, anchor_diag = _projection_dimension(
        source_card.get("source_anchors"), si_card.get("anchor_projections"), "source_anchor_id"
    )
    event_score, event_diag = _projection_dimension(
        source_card.get("source_events"), si_card.get("event_projections"), "source_event_id"
    )
    relation_score, relation_diag = _projection_dimension(
        source_card.get("source_relations"), si_card.get("relation_projections"),
        "source_relation_id", skip_statuses={"not_scored"},
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
    active_weight = sum(DIMENSION_WEIGHTS_V06[key] for key in active)
    no_decisions = any(
        diagnostics[key].get("decision_status") == "no_decisions"
        for key in ("anchor_fidelity", "event_fidelity", "relation_fidelity")
        if diagnostics[key].get("applicable")
    )
    final_score = None if no_decisions else round(
        sum(float(scores[key]) * DIMENSION_WEIGHTS_V06[key] for key in active) / active_weight,
        2,
    )
    uncertain = sum(
        int(diagnostics[key].get("uncertain_items", 0))
        for key in ("anchor_fidelity", "event_fidelity", "relation_fidelity")
    )
    inferred_hard_requirements = sum(
        1 for row in _records(si_card.get("anchor_projections")) + _records(si_card.get("event_projections"))
        if bool(row.get("hard_requirement", {}).get("required"))
        and row.get("hard_requirement", {}).get("basis") == "model_inference"
    )
    if no_decisions:
        status = "provisional_no_decisions"
    elif uncertain or inferred_hard_requirements:
        status = "provisional_review_required"
    else:
        status = "final"
    return {
        "dimension_scores": scores,
        "dimension_weights": DIMENSION_WEIGHTS_V06,
        "score_diagnostics": diagnostics,
        "final_score": final_score,
        "score_status": status,
    }


def _validate_projections(
    artifact: dict[str, Any], list_key: str, prefix: str, source_id_key: str,
    source_items: list[dict[str, Any]], target_units: list[dict[str, Any]],
    statuses: set[str], *, si_mode: bool, relation_mode: bool,
) -> list[str]:
    issues = _require_arrays(artifact, (list_key,))
    rows = _records(artifact.get(list_key))
    _sequential_ids(rows, "projection_id", prefix, list_key, issues)
    source_ids = [str(row.get(source_id_key)) for row in source_items]
    projected = [str(row.get(source_id_key) or "") for row in rows]
    if Counter(projected) != Counter(source_ids):
        issues.append(f"{list_key} must cover every source item exactly once")
    target_text = _unit_text(target_units, "target_unit_id", "target_text")
    for row in rows:
        projection_id = str(row.get("projection_id") or "")
        selected = _strings(row.get("target_unit_ids"))
        if any(unit_id not in target_text for unit_id in selected):
            issues.append(f"projection {projection_id} references unknown target unit")
        spans = _strings(row.get("target_spans"))
        if any(not any(span in target_text.get(unit_id, "") for unit_id in selected) for span in spans):
            issues.append(f"projection {projection_id} has non-verbatim target span")
        status = row.get("mapping_status")
        if status not in statuses:
            issues.append(f"projection {projection_id} has unsupported mapping_status")
        if status == "missing" and (selected or spans):
            issues.append(f"missing projection {projection_id} cannot cite target evidence")
        if status not in {"missing", "not_scored"} and not selected:
            issues.append(f"projection {projection_id} needs target units")
        if not _is_number(row.get("confidence")) or not 0 <= float(row["confidence"]) <= 1:
            issues.append(f"projection {projection_id} confidence must be between 0 and 1")
        if not str(row.get("reason") or "").strip():
            issues.append(f"projection {projection_id} needs a reason")
        if not relation_mode:
            requirement = row.get("hard_requirement")
            forbidden_keys = {
                "accepted_forms", "rejected_forms", "allowed_aliases", "forbidden_aliases"
            }
            if isinstance(requirement, dict) and forbidden_keys.intersection(requirement):
                issues.append(f"projection {projection_id} contains forbidden form lists")
            if not isinstance(requirement, dict) or not isinstance(requirement.get("required"), bool):
                issues.append(f"projection {projection_id} needs hard_requirement.required")
            elif requirement["required"]:
                requirement_type = requirement.get("requirement_type")
                if requirement_type not in HARD_REQUIREMENT_TYPES:
                    issues.append(f"projection {projection_id} has invalid hard requirement type")
                if requirement.get("basis") not in {
                    "verified_input", "intrinsic_exactness", "model_inference"
                }:
                    issues.append(f"projection {projection_id} has invalid hard requirement basis")
                if requirement_type == "exact_target_form" and not str(
                    requirement.get("required_target_form") or ""
                ).strip():
                    issues.append(f"projection {projection_id} exact form requirement needs one form")
                if requirement_type == "required_event_semantics" and not _strings(
                    requirement.get("required_semantics")
                ):
                    issues.append(f"projection {projection_id} event requirement needs semantics")
                if not str(requirement.get("reason") or "").strip():
                    issues.append(f"projection {projection_id} hard requirement needs a reason")
            elif isinstance(requirement, dict) and any([
                requirement.get("requirement_type") is not None,
                requirement.get("required_target_form") is not None,
                bool(requirement.get("required_semantics")),
                requirement.get("basis") is not None,
            ]):
                issues.append(f"projection {projection_id} disabled hard requirement must be empty")
            satisfied = row.get("hard_requirement_satisfied")
            if si_mode:
                if isinstance(requirement, dict) and requirement.get("required"):
                    if satisfied not in {True, False}:
                        issues.append(f"projection {projection_id} must decide hard requirement")
                    if satisfied is False and status != "contradiction":
                        issues.append(f"projection {projection_id} violated hard requirement must contradict")
                elif satisfied is not None:
                    issues.append(f"projection {projection_id} has no hard requirement to satisfy")
            elif satisfied is not None:
                issues.append(f"reference projection {projection_id} must not pre-judge satisfaction")
    return issues


def _validate_aggregate_status(
    projection_id: str, mapping_status: Any, statuses: list[Any], issues: list[str]
) -> None:
    if not statuses or any(status not in COMPONENT_STATUSES for status in statuses):
        return
    if "contradicted" in statuses and mapping_status != "contradiction":
        issues.append(f"projection {projection_id} component contradiction must control mapping_status")
    elif "uncertain" in statuses and mapping_status != "uncertain":
        issues.append(f"projection {projection_id} uncertain component must control mapping_status")
    elif "omitted" in statuses and mapping_status not in {"partial", "missing"}:
        issues.append(f"projection {projection_id} omitted component requires partial or missing")
    elif set(statuses) == {"preserved"} and mapping_status != "equivalent":
        issues.append(f"projection {projection_id} all preserved components require equivalent")


def _projection_dimension(
    source_items_value: Any, projections_value: Any, source_id_key: str,
    skip_statuses: set[str] | None = None,
) -> tuple[float | None, dict[str, Any]]:
    source_items = _records(source_items_value)
    projections = {str(row.get(source_id_key)): row for row in _records(projections_value)}
    if not source_items:
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
    for item in source_items:
        projection = projections.get(str(item.get(source_id_key)), {})
        status = str(projection.get("mapping_status") or "uncertain")
        weight = float(item.get("importance", 1))
        decision = {
            source_id_key: str(item.get(source_id_key) or ""),
            "projection_id": projection.get("projection_id"),
            "importance": weight,
            "mapping_status": status,
            "score_value": None,
            "weighted_contribution": None,
        }
        if source_id_key == "source_anchor_id":
            decision["component_statuses"] = {
                str(row.get("component") or ""): row.get("status")
                for row in _records(projection.get("component_results"))
            }
        elif source_id_key == "source_event_id":
            decision["event_substatuses"] = {
                key: projection.get(key)
                for key in ("predicate_status", "argument_status", "operator_status")
            }
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
        return None, {
            "applicable": True, "decision_status": "no_decisions",
            "total_items": len(source_items), "decided_items": 0,
            "uncertain_items": uncertain, "blocked_items": blocked,
            "decided_weight": 0.0, "earned_weight": 0.0,
            "item_decisions": item_decisions,
        }
    status = "complete" if uncertain == 0 else "partial_decisions"
    return round(100 * earned / decided_weight, 2), {
        "applicable": True, "decision_status": status,
        "total_items": len(source_items),
        "decided_items": len(source_items) - uncertain - blocked,
        "uncertain_items": uncertain, "blocked_items": blocked,
        "decided_weight": decided_weight, "earned_weight": earned,
        "item_decisions": item_decisions,
    }


def _delivery_score(issues: list[dict[str, Any]]) -> float:
    deduction = sum(SEVERITY_DEDUCTIONS_V06.get(str(row.get("severity")), 0) for row in issues)
    return round(max(0.0, 100.0 - deduction), 2)


def _require_arrays(artifact: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [f"{field} must be an array" for field in fields if not isinstance(artifact.get(field), list)]


def _sequential_ids(
    rows: list[dict[str, Any]], key: str, prefix: str, label: str, issues: list[str]
) -> None:
    expected = [f"{prefix}{index}" for index in range(1, len(rows) + 1)]
    actual = [str(row.get(key) or "") for row in rows]
    if actual != expected:
        issues.append(f"{label} IDs must be sequential: expected {expected}, got {actual}")


def _verbatim(value: Any, text: str, label: str, issues: list[str]) -> None:
    span = str(value or "")
    if not span or span not in text:
        issues.append(f"{label} has non-verbatim evidence")


def _unit_text(rows: list[dict[str, Any]], id_key: str, text_key: str) -> dict[str, str]:
    return {str(row.get(id_key)): str(row.get(text_key) or "") for row in rows}


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _same_component_value(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if left is None or right is None:
        return left is right
    return str(left).strip() == str(right).strip()
