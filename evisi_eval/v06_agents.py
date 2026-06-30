"""Agents for the v0.6 source-conditioned extraction and projection workflow."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .agents import FluencyAgent, Runner, SIExpressionAgent, StageResult
from .llm_provider import LLMClient
from .prompt_loader import prompt_manifest
from .v06_validation import (
    PROTOCOL_VERSION_V06,
    calculate_v06_scores,
    validate_anchor_projections,
    validate_event_projections,
    validate_relation_projections,
    validate_requirement_inheritance,
    validate_source_anchors,
    validate_source_events,
    validate_source_relations,
    validate_source_segments,
    validate_target_alignment,
)


class V06SourceCardBuilder:
    """Build the source authority card through four focused semantic calls."""

    def __init__(self, client: LLMClient):
        self.client = client
        self.runner = Runner(client)

    def build(self, sample: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        sample_id = _required(sample, "sample_id")
        source_text = _required(sample, "source_text")
        common = {
            "sample_id": sample_id,
            "src_lang": sample.get("src_lang", "unspecified"),
            "tgt_lang": sample.get("tgt_lang", "unspecified"),
            "domain": sample.get("domain", "unspecified"),
        }
        segment_result = self.runner.run(
            "v06_source_segment_agent",
            {**common, "source_text": source_text},
            lambda artifact: validate_source_segments(artifact, source_text),
        )
        segments = _records(segment_result.artifact.get("source_segments"))
        anchor_result = self.runner.run(
            "v06_source_anchor_agent",
            {
                **common,
                "source_segments": segments,
                "provided_hard_requirements": _records(sample.get("hard_requirements")),
            },
            lambda artifact: validate_source_anchors(artifact, segments),
        )
        anchors = _records(anchor_result.artifact.get("source_anchors"))
        event_result = self.runner.run(
            "v06_source_event_agent",
            {**common, "source_segments": segments, "source_anchors": anchors},
            lambda artifact: validate_source_events(artifact, segments, anchors),
        )
        events = _records(event_result.artifact.get("source_events"))
        relation_result = self.runner.run(
            "v06_source_relation_agent",
            {**common, "source_segments": segments, "source_events": events},
            lambda artifact: validate_source_relations(artifact, segments, events),
        )
        relations = _records(relation_result.artifact.get("source_relations"))
        stage_results = [segment_result, anchor_result, event_result, relation_result]
        card = {
            **common,
            "source_text": source_text,
            "source_segments": segments,
            "source_anchors": anchors,
            "source_events": events,
            "source_relations": relations,
            "provided_hard_requirements": _records(sample.get("hard_requirements")),
            "metadata": {
                "protocol_version": PROTOCOL_VERSION_V06,
                "provider": self.client.provider_name,
                "model": self.client.model_name,
                "source_is_semantic_authority": True,
                "frozen_before_reference_and_si_projection": True,
                "prompt_hashes": prompt_manifest(),
                "stage_validation": _stage_validation(stage_results),
                "agent_trace": _stage_traces(stage_results),
            },
        }
        card["metadata"]["source_card_hash"] = artifact_hash(card)
        return card, card["metadata"]["agent_trace"]


class V06ProjectionBuilder:
    """Project source obligations into a reference or SI translation."""

    def __init__(self, client: LLMClient, mode: str):
        if mode not in {"reference", "si"}:
            raise ValueError("projection mode must be reference or si")
        self.client = client
        self.mode = mode
        self.runner = Runner(client)

    def build(
        self,
        source_card: dict[str, Any],
        translation: str,
        *,
        system_name: str | None = None,
        reference_card: dict[str, Any] | None = None,
        evaluation_context: dict[str, Any] | None = None,
        reference_type: str = "unspecified",
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        sample_id = _required(source_card, "sample_id")
        if not translation.strip():
            raise ValueError(f"{self.mode} translation is required")
        identity = {
            "sample_id": sample_id,
            "translation_role": self.mode,
            "system_name": "anonymous_system" if self.mode == "si" else "reference",
        }
        alignment = self.runner.run(
            "v06_target_alignment_agent",
            {
                **identity,
                "source_segments": source_card["source_segments"],
                "target_translation": translation,
            },
            lambda artifact: validate_target_alignment(
                artifact, source_card["source_segments"], translation
            ),
        )
        target_units = _records(alignment.artifact.get("target_units"))
        projection_context = {
            **identity,
            "source_card": _source_projection_view(source_card),
            "target_units": target_units,
            "reference_type": reference_type,
            "provided_hard_requirements": source_card.get("provided_hard_requirements", []),
        }
        if self.mode == "si":
            if reference_card is None:
                raise ValueError("SI projection requires a frozen reference projection card")
            if evaluation_context is None:
                raise ValueError("SI projection requires a frozen evaluation context")
            context_issues = validate_evaluation_context_v06(
                evaluation_context, source_card, reference_card
            )
            if context_issues:
                raise ValueError("invalid evaluation context: " + "; ".join(context_issues))
            projection_context["reference_projection_card"] = _reference_projection_view(
                reference_card
            )

        anchor_result = self.runner.run(
            f"v06_{self.mode}_anchor_projection_agent",
            projection_context,
            lambda artifact: (
                validate_anchor_projections(
                    artifact, source_card["source_anchors"], target_units,
                    si_mode=self.mode == "si",
                )
                + (
                    validate_requirement_inheritance(
                        artifact, reference_card, "anchor_projections", "source_anchor_id"
                    )
                    if self.mode == "si" and reference_card is not None else []
                )
            ),
        )
        anchor_projections = _records(anchor_result.artifact.get("anchor_projections"))
        event_result = self.runner.run(
            f"v06_{self.mode}_event_projection_agent",
            {**projection_context, "anchor_projections": anchor_projections},
            lambda artifact: (
                validate_event_projections(
                    artifact, source_card["source_events"], target_units,
                    si_mode=self.mode == "si",
                )
                + (
                    validate_requirement_inheritance(
                        artifact, reference_card, "event_projections", "source_event_id"
                    )
                    if self.mode == "si" and reference_card is not None else []
                )
            ),
        )
        event_projections = _records(event_result.artifact.get("event_projections"))
        relation_result = self.runner.run(
            f"v06_{self.mode}_relation_projection_agent",
            {
                **projection_context,
                "anchor_projections": anchor_projections,
                "event_projections": event_projections,
            },
            lambda artifact: validate_relation_projections(
                artifact, source_card["source_relations"], target_units,
                si_mode=self.mode == "si", event_projections=event_projections,
            ),
        )
        relation_projections = _records(relation_result.artifact.get("relation_projections"))
        stage_results = [alignment, anchor_result, event_result, relation_result]
        card = {
            "sample_id": sample_id,
            "translation_role": self.mode,
            "system_name": system_name if self.mode == "si" else "reference",
            "target_translation": translation,
            "source_card_hash": source_card["metadata"]["source_card_hash"],
            "target_units": target_units,
            "anchor_projections": anchor_projections,
            "event_projections": event_projections,
            "relation_projections": relation_projections,
            "target_additions": {
                "anchors": _records(anchor_result.artifact.get("target_additions")),
                "events": _records(event_result.artifact.get("target_additions")),
                "relations": _records(relation_result.artifact.get("target_additions")),
            },
            "metadata": {
                "protocol_version": PROTOCOL_VERSION_V06,
                "provider": self.client.provider_name,
                "model": self.client.model_name,
                "source_conditioned_projection": True,
                "reference_is_auxiliary": self.mode == "si",
                "reference_type": reference_type,
                "stage_validation": _stage_validation(stage_results),
                "agent_trace": _stage_traces(stage_results),
            },
        }
        if self.mode == "si":
            card["reference_card_hash"] = reference_card["metadata"]["reference_card_hash"]
            card["evaluation_context_hash"] = evaluation_context["metadata"][
                "evaluation_context_hash"
            ]
        card["metadata"][f"{self.mode}_card_hash"] = artifact_hash(card)
        return card, card["metadata"]["agent_trace"]


class V06EvaluationLoop:
    """Build SI projections, delivery judgements, and deterministic v0.6 scores."""

    def __init__(self, client: LLMClient):
        self.client = client
        self.si_builder = V06ProjectionBuilder(client, "si")
        self.fluency = FluencyAgent(client)
        self.expression = SIExpressionAgent(client)

    def run(
        self, source_card: dict[str, Any], reference_card: dict[str, Any],
        evaluation_context: dict[str, Any], output: dict[str, Any], reference_type: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        sample_id = _required(output, "sample_id")
        system_name = _required(output, "system_name")
        translation = _required(output, "si_translation")
        if sample_id != source_card["sample_id"] or sample_id != reference_card["sample_id"]:
            raise ValueError("sample identity mismatch across source/reference/SI")
        si_card, traces = self.si_builder.build(
            source_card,
            translation,
            system_name=system_name,
            reference_card=reference_card,
            evaluation_context=evaluation_context,
            reference_type=reference_type,
        )
        fluency = self.fluency.evaluate(sample_id, translation)
        expression = self.expression.evaluate(source_card, translation)
        traces.extend(fluency.traces)
        traces.extend(expression.traces)
        fluency_issues = _records(fluency.artifact.get("fluency_issues"))
        expression_issues = _records(expression.artifact.get("si_expression_issues"))
        score = calculate_v06_scores(
            source_card, si_card, fluency_issues, expression_issues
        )
        result = {
            "sample_id": sample_id,
            "system_name": system_name,
            "source_text": source_card["source_text"],
            "reference_translation": reference_card["target_translation"],
            "si_translation": translation,
            "source_card_hash": source_card["metadata"]["source_card_hash"],
            "reference_card_hash": reference_card["metadata"]["reference_card_hash"],
            "evaluation_context_hash": evaluation_context["metadata"][
                "evaluation_context_hash"
            ],
            "si_card_hash": si_card["metadata"]["si_card_hash"],
            "source_segments": source_card["source_segments"],
            "source_anchors": source_card["source_anchors"],
            "source_events": source_card["source_events"],
            "source_relations": source_card["source_relations"],
            "reference_projections": {
                "anchors": reference_card["anchor_projections"],
                "events": reference_card["event_projections"],
                "relations": reference_card["relation_projections"],
            },
            "si_target_units": si_card["target_units"],
            "anchor_projections": si_card["anchor_projections"],
            "event_projections": si_card["event_projections"],
            "relation_projections": si_card["relation_projections"],
            "target_additions": si_card["target_additions"],
            "fluency_issues": fluency_issues,
            "fluency_assessment": str(fluency.artifact.get("fluency_assessment") or ""),
            "si_expression_issues": expression_issues,
            "si_expression_assessment": str(
                expression.artifact.get("si_expression_assessment") or ""
            ),
            **score,
            "metadata": {
                "protocol_version": PROTOCOL_VERSION_V06,
                "reference_is_auxiliary": True,
                "reference_difference_is_not_automatic_error": True,
                "agent_trace": traces,
                "prompt_hashes": prompt_manifest(),
            },
        }
        return result, si_card


def validate_source_card_v06(card: dict[str, Any]) -> list[str]:
    issues = validate_source_segments(card, str(card.get("source_text") or ""))
    issues.extend(validate_source_anchors(card, _records(card.get("source_segments"))))
    issues.extend(validate_source_events(
        card, _records(card.get("source_segments")), _records(card.get("source_anchors"))
    ))
    issues.extend(validate_source_relations(
        card, _records(card.get("source_segments")), _records(card.get("source_events"))
    ))
    return issues


def validate_projection_card_v06(
    card: dict[str, Any], source_card: dict[str, Any], *, si_mode: bool,
    reference_card: dict[str, Any] | None = None,
    evaluation_context: dict[str, Any] | None = None,
) -> list[str]:
    issues = validate_target_alignment(
        {"target_units": card.get("target_units")},
        source_card["source_segments"],
        str(card.get("target_translation") or ""),
    )
    target_units = _records(card.get("target_units"))
    issues.extend(validate_anchor_projections(
        card, source_card["source_anchors"], target_units, si_mode=si_mode
    ))
    issues.extend(validate_event_projections(
        card, source_card["source_events"], target_units, si_mode=si_mode
    ))
    issues.extend(validate_relation_projections(
        card, source_card["source_relations"], target_units, si_mode=si_mode,
        event_projections=_records(card.get("event_projections")),
    ))
    if card.get("source_card_hash") != source_card.get("metadata", {}).get("source_card_hash"):
        issues.append("projection card source_card_hash does not match source card")
    if si_mode:
        if reference_card is None or evaluation_context is None:
            issues.append("SI projection validation requires reference card and evaluation context")
        else:
            issues.extend(validate_evaluation_context_v06(
                evaluation_context, source_card, reference_card
            ))
            if card.get("reference_card_hash") != reference_card.get("metadata", {}).get(
                "reference_card_hash"
            ):
                issues.append("SI projection reference_card_hash does not match reference card")
            if card.get("evaluation_context_hash") != evaluation_context.get("metadata", {}).get(
                "evaluation_context_hash"
            ):
                issues.append("SI projection evaluation_context_hash does not match context")
    return issues


def build_evaluation_context_v06(
    source_card: dict[str, Any], reference_card: dict[str, Any]
) -> dict[str, Any]:
    """Bind frozen source/reference artifacts without changing semantic authority."""
    sample_id = _required(source_card, "sample_id")
    if sample_id != _required(reference_card, "sample_id"):
        raise ValueError("source/reference sample identity mismatch")
    source_hash = str(source_card.get("metadata", {}).get("source_card_hash") or "")
    reference_hash = str(reference_card.get("metadata", {}).get("reference_card_hash") or "")
    if not source_hash or not reference_hash:
        raise ValueError("source and reference cards must be frozen before context construction")
    if reference_card.get("source_card_hash") != source_hash:
        raise ValueError("reference card is not derived from the supplied source card")

    context = {
        "sample_id": sample_id,
        "source_card_hash": source_hash,
        "reference_card_hash": reference_hash,
        "reference_type": reference_card.get("metadata", {}).get(
            "reference_type", "unspecified"
        ),
        "item_links": {
            "anchors": _context_links(
                source_card.get("source_anchors"), reference_card.get("anchor_projections"),
                "source_anchor_id",
            ),
            "events": _context_links(
                source_card.get("source_events"), reference_card.get("event_projections"),
                "source_event_id",
            ),
            "relations": _context_links(
                source_card.get("source_relations"), reference_card.get("relation_projections"),
                "source_relation_id",
            ),
        },
        "metadata": {
            "protocol_version": PROTOCOL_VERSION_V06,
            "source_is_semantic_authority": True,
            "reference_is_auxiliary": True,
            "constructed_without_llm": True,
        },
    }
    context["metadata"]["evaluation_context_hash"] = artifact_hash(context)
    issues = validate_evaluation_context_v06(context, source_card, reference_card)
    if issues:
        raise ValueError("invalid evaluation context: " + "; ".join(issues))
    return context


def validate_evaluation_context_v06(
    context: dict[str, Any], source_card: dict[str, Any], reference_card: dict[str, Any]
) -> list[str]:
    issues: list[str] = []
    if context.get("sample_id") != source_card.get("sample_id") or context.get(
        "sample_id"
    ) != reference_card.get("sample_id"):
        issues.append("evaluation context sample identity mismatch")
    source_hash = source_card.get("metadata", {}).get("source_card_hash")
    reference_hash = reference_card.get("metadata", {}).get("reference_card_hash")
    if context.get("source_card_hash") != source_hash:
        issues.append("evaluation context source_card_hash mismatch")
    if context.get("reference_card_hash") != reference_hash:
        issues.append("evaluation context reference_card_hash mismatch")
    if reference_card.get("source_card_hash") != source_hash:
        issues.append("reference card source_card_hash mismatch")
    expected_links = {
        "anchors": _context_links(
            source_card.get("source_anchors"), reference_card.get("anchor_projections"),
            "source_anchor_id",
        ),
        "events": _context_links(
            source_card.get("source_events"), reference_card.get("event_projections"),
            "source_event_id",
        ),
        "relations": _context_links(
            source_card.get("source_relations"), reference_card.get("relation_projections"),
            "source_relation_id",
        ),
    }
    if context.get("item_links") != expected_links:
        issues.append("evaluation context item links do not match frozen cards")
    expected_hash = str(context.get("metadata", {}).get("evaluation_context_hash") or "")
    if not expected_hash or expected_hash != artifact_hash(context):
        issues.append("evaluation context hash mismatch")
    return issues


def artifact_hash(artifact: dict[str, Any]) -> str:
    payload = {key: value for key, value in artifact.items() if key != "metadata"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _source_projection_view(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_segments": card["source_segments"],
        "source_anchors": card["source_anchors"],
        "source_events": card["source_events"],
        "source_relations": card["source_relations"],
    }


def _reference_projection_view(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_units": card["target_units"],
        "anchor_projections": card["anchor_projections"],
        "event_projections": card["event_projections"],
        "relation_projections": card["relation_projections"],
        "reference_type": card.get("metadata", {}).get("reference_type", "unspecified"),
    }


def _context_links(
    source_items_value: Any, projections_value: Any, source_id_key: str
) -> list[dict[str, Any]]:
    projections = {
        str(row.get(source_id_key)): row for row in _records(projections_value)
    }
    return [
        {
            source_id_key: source_id,
            "reference_projection_id": projections.get(source_id, {}).get("projection_id"),
            "reference_mapping_status": projections.get(source_id, {}).get("mapping_status"),
        }
        for row in _records(source_items_value)
        for source_id in [str(row.get(source_id_key) or "")]
    ]


def _stage_validation(results: list[StageResult]) -> list[dict[str, Any]]:
    return [
        {
            "initial_issues": result.initial_issues,
            "repair_count": max(0, len(result.traces) - 1),
            "normalization_notes": getattr(result, "normalization_notes", []),
        }
        for result in results
    ]


def _stage_traces(results: list[StageResult]) -> list[dict[str, Any]]:
    return [trace for result in results for trace in result.traces]


def _required(row: dict[str, Any], key: str) -> str:
    value = str(row.get(key) or "")
    if not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
