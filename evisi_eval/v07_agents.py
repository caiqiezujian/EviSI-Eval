"""Agents for the v0.7 joint-card extraction and positional matching workflow.

  - Joint Source+Reference extraction (8 LLM calls → frozen Joint Card)
  - Positional SI matching (6 LLM calls per system → deterministic scoring)
  - No protocol injection (all prompts self-contained)
  - Positional array alignment (not ID cross-references)
  - Flat JSON output (no component_results, operators grids, hard_requirement structures)
  - Joint Card = Python zip of source + reference outputs
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .agents import FluencyAgent, Runner, SIExpressionAgent, StageResult
from .io_utils import read_json, write_json
from .llm_provider import LLMClient
from .prompt_loader import prompt_manifest
from .v07_validation import (
    PROTOCOL_VERSION_V07,
    calculate_v07_scores,
    validate_joint_card_assembly,
    validate_reference_alignment,
    validate_reference_anchors,
    validate_reference_events,
    validate_reference_relations,
    validate_si_alignment,
    validate_si_anchor_matches,
    validate_si_event_matches,
    validate_si_relation_matches,
    validate_source_anchors,
    validate_source_events,
    validate_source_relations,
    validate_source_segments,
)


class V07JointCardBuilder:
    """Build the frozen Joint Card from Source + Reference (8 LLM calls)."""

    def __init__(self, client: LLMClient):
        self.client = client
        self.runner = Runner(client)

    def build(
        self, sample: dict[str, Any], *,
        stage_cache_dir: str | Path | None = None,
        resume: bool = False,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        sample_id = _required(sample, "sample_id")
        source_text = _required(sample, "source_text")
        reference_translation = _required(sample, "reference_translation")
        common = {
            "sample_id": sample_id,
            "src_lang": sample.get("src_lang", "unspecified"),
            "tgt_lang": sample.get("tgt_lang", "unspecified"),
            "domain": sample.get("domain", "unspecified"),
        }

        # ── Source side (4 calls) ──────────────────────────────────
        # Phase 1: Segment
        seg_result = _run_cached_stage(
            self.runner,
            "v07_source_segment",
            {**common, "source_text": source_text},
            lambda a: validate_source_segments(a, source_text),
            _cache(stage_cache_dir, "01_source_segments.json"), resume,
        )
        source_segments = _records(seg_result.artifact.get("source_segments"))

        # Phase 2: Anchor
        anchor_result = _run_cached_stage(
            self.runner,
            "v07_source_anchor",
            {**common, "source_segments": source_segments},
            lambda a: validate_source_anchors(a, source_segments),
            _cache(stage_cache_dir, "02_source_anchors.json"), resume,
        )
        source_anchors = _records(anchor_result.artifact.get("source_anchors"))

        # Phase 3: Event
        event_result = _run_cached_stage(
            self.runner,
            "v07_source_event",
            {**common, "source_segments": source_segments},
            lambda a: validate_source_events(a, source_segments),
            _cache(stage_cache_dir, "03_source_events.json"), resume,
        )
        source_events = _records(event_result.artifact.get("source_events"))

        # Phase 4: Relation
        relation_result = _run_cached_stage(
            self.runner,
            "v07_source_relation",
            {**common, "source_segments": source_segments, "source_events": source_events},
            lambda a: validate_source_relations(a, source_events),
            _cache(stage_cache_dir, "04_source_relations.json"), resume,
        )
        source_relations = _records(relation_result.artifact.get("source_relations"))

        # ── Reference side (4 calls) ───────────────────────────────
        # Phase 5: Reference Align
        ref_align_result = _run_cached_stage(
            self.runner,
            "v07_reference_align",
            {**common, "source_segments": source_segments,
             "reference_translation": reference_translation},
            lambda a: validate_reference_alignment(a, source_segments, reference_translation),
            _cache(stage_cache_dir, "05_reference_segments.json"), resume,
        )
        reference_segments = _records(ref_align_result.artifact.get("reference_segments"))

        # Phase 6: Reference Anchor
        ref_anchor_result = _run_cached_stage(
            self.runner,
            "v07_reference_anchor",
            {
                **common,
                "source_segments": source_segments,
                "source_anchors": source_anchors,
                "reference_segments": reference_segments,
                "reference_translation": reference_translation,
            },
            lambda a: validate_reference_anchors(a, source_anchors, reference_segments),
            _cache(stage_cache_dir, "06_reference_anchors.json"), resume,
        )
        reference_anchors = _records(ref_anchor_result.artifact.get("reference_anchors"))

        # Phase 7: Reference Event
        ref_event_result = _run_cached_stage(
            self.runner,
            "v07_reference_event",
            {
                **common,
                "source_segments": source_segments,
                "source_events": source_events,
                "reference_segments": reference_segments,
                "reference_translation": reference_translation,
            },
            lambda a: validate_reference_events(a, source_events, reference_segments),
            _cache(stage_cache_dir, "07_reference_events.json"), resume,
        )
        reference_events = _records(ref_event_result.artifact.get("reference_events"))

        # Phase 8: Reference Relation
        ref_relation_result = _run_cached_stage(
            self.runner,
            "v07_reference_relation",
            {
                **common,
                "source_relations": source_relations,
                "reference_events": reference_events,
                "reference_translation": reference_translation,
            },
            lambda a: validate_reference_relations(a, source_relations),
            _cache(stage_cache_dir, "08_reference_relations.json"), resume,
        )
        reference_relations = _records(ref_relation_result.artifact.get("reference_relations"))

        # ── Assemble Joint Card ────────────────────────────────────
        assembly_issues = validate_joint_card_assembly(
            source_segments, source_anchors, source_events, source_relations,
            reference_segments, reference_anchors, reference_events, reference_relations,
        )
        if assembly_issues:
            raise ValueError("joint card assembly failed: " + "; ".join(assembly_issues))

        joint_card = _assemble_joint_card(
            sample_id, source_text, reference_translation,
            source_segments, source_anchors, source_events, source_relations,
            reference_segments, reference_anchors, reference_events, reference_relations,
            _stage_traces([
                seg_result, anchor_result, event_result, relation_result,
                ref_align_result, ref_anchor_result, ref_event_result, ref_relation_result,
            ]),
            self.client,
        )

        return joint_card, joint_card["metadata"]["agent_trace"]


class V07SIMatcher:
    """Match one SI system against the frozen Joint Card (6 LLM calls)."""

    def __init__(self, client: LLMClient):
        self.client = client
        self.runner = Runner(client)
        self.fluency = FluencyAgent(client)
        self.expression = SIExpressionAgent(client)

    def evaluate(
        self, joint_card: dict[str, Any], output: dict[str, Any], *,
        stage_cache_dir: str | Path | None = None,
        resume: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        sample_id = _required(output, "sample_id")
        system_name = _required(output, "system_name")
        si_translation = _required(output, "si_translation")
        if sample_id != joint_card["sample_id"]:
            raise ValueError("SI output sample_id does not match joint card")

        identity = {
            "sample_id": sample_id,
            "system_name": "anonymous_system",
        }
        source_segments = _records(joint_card.get("source_segments"))

        # Phase 9: SI Align
        si_align_result = _run_cached_stage(
            self.runner,
            "v07_si_align",
            {**identity, "source_segments": source_segments,
             "si_translation": si_translation},
            lambda a: validate_si_alignment(a, source_segments, si_translation),
            _cache(stage_cache_dir, "09_si_segments.json"), resume,
        )
        si_segments = _records(si_align_result.artifact.get("si_segments"))

        # Phase 10: SI Anchor Match
        anchor_match_result = _run_cached_stage(
            self.runner,
            "v07_si_anchor_match",
            {
                **identity,
                "source_segments": source_segments,
                "joint_anchors": joint_card["flat_anchors"],
                "si_segments": si_segments,
                "si_translation": si_translation,
            },
            lambda a: validate_si_anchor_matches(a, joint_card["flat_anchors"], si_segments),
            _cache(stage_cache_dir, "10_anchor_matches.json"), resume,
        )
        anchor_matches = _records(anchor_match_result.artifact.get("anchor_matches"))

        # Phase 11: SI Event Match
        event_match_result = _run_cached_stage(
            self.runner,
            "v07_si_event_match",
            {
                **identity,
                "source_events": _records(joint_card.get("source_events")),
                "joint_events": joint_card["flat_events"],
                "si_segments": si_segments,
                "si_translation": si_translation,
            },
            lambda a: validate_si_event_matches(a, joint_card["flat_events"], si_segments),
            _cache(stage_cache_dir, "11_event_matches.json"), resume,
        )
        event_matches = _records(event_match_result.artifact.get("event_matches"))

        # Phase 12: SI Relation Match
        relation_match_result = _run_cached_stage(
            self.runner,
            "v07_si_relation_match",
            {
                **identity,
                "source_relations": _records(joint_card.get("source_relations")),
                "joint_relations": joint_card["flat_relations"],
                "si_event_matches": event_matches,
                "si_translation": si_translation,
            },
            lambda a: validate_si_relation_matches(
                a, joint_card["flat_relations"], event_matches,
            ),
            _cache(stage_cache_dir, "12_relation_matches.json"), resume,
        )
        relation_matches = _records(relation_match_result.artifact.get("relation_matches"))

        # Phase 13-14: Delivery
        fluency = self.fluency.evaluate(sample_id, si_translation)
        expression = self.expression.evaluate(
            {"sample_id": sample_id, "source_text": joint_card["source_text"]},
            si_translation,
        )

        fluency_issues = _records(fluency.artifact.get("fluency_issues"))
        expression_issues = _records(expression.artifact.get("si_expression_issues"))

        # ── Deterministic scoring ──────────────────────────────────
        score = calculate_v07_scores(
            joint_card["flat_anchors"],
            joint_card["flat_events"],
            joint_card["flat_relations"],
            anchor_matches,
            event_matches,
            relation_matches,
            fluency_issues,
            expression_issues,
        )

        traces = _stage_traces([
            si_align_result, anchor_match_result, event_match_result,
            relation_match_result,
        ])
        traces.extend(fluency.traces)
        traces.extend(expression.traces)

        si_card = {
            "sample_id": sample_id,
            "system_name": system_name,
            "si_translation": si_translation,
            "joint_card_hash": joint_card["metadata"]["joint_card_hash"],
            "si_segments": si_segments,
            "anchor_matches": anchor_matches,
            "event_matches": event_matches,
            "relation_matches": relation_matches,
            "fluency_issues": fluency_issues,
            "si_expression_issues": expression_issues,
            "metadata": {
                "protocol_version": PROTOCOL_VERSION_V07,
                "provider": self.client.provider_name,
                "model": self.client.model_name,
                "agent_trace": traces,
            },
        }

        result = {
            "sample_id": sample_id,
            "system_name": system_name,
            "source_text": joint_card["source_text"],
            "reference_translation": joint_card["reference_translation"],
            "si_translation": si_translation,
            "joint_card_hash": joint_card["metadata"]["joint_card_hash"],
            "si_segments": si_segments,
            "anchor_matches": anchor_matches,
            "event_matches": event_matches,
            "relation_matches": relation_matches,
            "fluency_issues": fluency_issues,
            "fluency_assessment": str(fluency.artifact.get("fluency_assessment") or ""),
            "si_expression_issues": expression_issues,
            "si_expression_assessment": str(
                expression.artifact.get("si_expression_assessment") or ""
            ),
            **score,
            "metadata": {
                "protocol_version": PROTOCOL_VERSION_V07,
                "source_is_semantic_authority": True,
                "reference_is_auxiliary": True,
                "agent_trace": traces,
                "prompt_hashes": prompt_manifest(),
            },
        }
        return result, si_card


# ── Joint Card Assembly (Python, zero LLM) ──────────────────────────

def _assemble_joint_card(
    sample_id: str,
    source_text: str,
    reference_translation: str,
    source_segments: list[dict[str, Any]],
    source_anchors: list[dict[str, Any]],
    source_events: list[dict[str, Any]],
    source_relations: list[dict[str, Any]],
    reference_segments: list[dict[str, Any]],
    reference_anchors: list[dict[str, Any]],
    reference_events: list[dict[str, Any]],
    reference_relations: list[dict[str, Any]],
    traces: list[dict[str, Any]],
    client: LLMClient,
) -> dict[str, Any]:
    """Zip source and reference sides into the frozen Joint Card."""

    # Build per-segment lookups so assembly is robust to LLM ordering quirks.
    ref_seg_by_id: dict[str, dict[str, Any]] = {
        str(r.get("seg_id") or ""): r for r in reference_segments
    }
    ref_anchors_by_seg: dict[str, list[dict[str, Any]]] = {}
    ref_events_by_seg: dict[str, list[dict[str, Any]]] = {}
    for ra in reference_anchors:
        ref_anchors_by_seg.setdefault(str(ra.get("seg_id") or ""), []).append(ra)
    for re_ in reference_events:
        ref_events_by_seg.setdefault(str(re_.get("seg_id") or ""), []).append(re_)

    # Build segment-level merged view
    segments: list[dict[str, Any]] = []
    for seg in source_segments:
        seg_id = str(seg.get("seg_id") or "")
        ref_seg = ref_seg_by_id.get(seg_id, {})
        seg_source_anchors = [
            a for a in source_anchors if str(a.get("seg_id") or "") == seg_id
        ]
        seg_source_events = [
            e for e in source_events if str(e.get("seg_id") or "") == seg_id
        ]
        seg_ref_anchors = ref_anchors_by_seg.get(seg_id, [])
        seg_ref_events = ref_events_by_seg.get(seg_id, [])

        seg_anchors: list[dict[str, Any]] = []
        for sa, ra in zip(seg_source_anchors, seg_ref_anchors):
            seg_anchors.append({
                "anchor_id": sa.get("anchor_id"),
                "seg_id": seg_id,
                "type": sa.get("type"),
                "source_text": sa.get("text"),
                "source_evidence": sa.get("evidence"),
                "reference_text": ra.get("text"),
                "reference_evidence": ra.get("evidence"),
                "importance": sa.get("importance"),
            })

        seg_events: list[dict[str, Any]] = []
        for se, re_ in zip(seg_source_events, seg_ref_events):
            seg_events.append({
                "event_id": se.get("event_id"),
                "seg_id": seg_id,
                "type": se.get("type"),
                "source_summary": se.get("summary"),
                "source_evidence": se.get("evidence"),
                "reference_summary": re_.get("summary"),
                "reference_evidence": re_.get("evidence"),
                "importance": se.get("importance"),
            })

        segments.append({
            "seg_id": seg_id,
            "source_text": seg.get("source_text"),
            "reference_text": ref_seg.get("reference_text"),
            "anchors": seg_anchors,
            "events": seg_events,
        })

    # Merge relations
    relations: list[dict[str, Any]] = []
    for sr, rr in zip(source_relations, reference_relations):
        relations.append({
            "relation_id": sr.get("relation_id"),
            "type": sr.get("type"),
            "source_summary": sr.get("summary"),
            "source_evidence": sr.get("evidence"),
            "source_event_ids": sr.get("source_event_ids"),
            "reference_preserved": rr.get("preserved"),
            "reference_summary": rr.get("summary"),
            "importance": sr.get("importance"),
        })

    # Flat views for SI matching
    flat_anchors: list[dict[str, Any]] = []
    flat_events: list[dict[str, Any]] = []
    for seg in segments:
        flat_anchors.extend(seg["anchors"])
        flat_events.extend(seg["events"])

    card: dict[str, Any] = {
        "sample_id": sample_id,
        "source_text": source_text,
        "reference_translation": reference_translation,
        "source_segments": source_segments,
        "source_anchors": source_anchors,
        "source_events": source_events,
        "source_relations": source_relations,
        "reference_segments": reference_segments,
        "reference_anchors": reference_anchors,
        "reference_events": reference_events,
        "reference_relations": reference_relations,
        "segments": segments,
        "relations": relations,
        "flat_anchors": flat_anchors,
        "flat_events": flat_events,
        "flat_relations": relations,
        "metadata": {
            "protocol_version": PROTOCOL_VERSION_V07,
            "provider": client.provider_name,
            "model": client.model_name,
            "source_is_semantic_authority": True,
            "reference_is_auxiliary": True,
            "constructed_without_llm": True,
            "agent_trace": traces,
            "prompt_hashes": prompt_manifest(),
        },
    }
    card["metadata"]["joint_card_hash"] = artifact_hash(card)
    return card


# ── shared utilities ────────────────────────────────────────────────

def artifact_hash(artifact: dict[str, Any]) -> str:
    payload = {k: v for k, v in artifact.items() if k != "metadata"}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _run_cached_stage(
    runner: Runner, prompt_name: str, payload: dict[str, Any],
    validator: Any, cache_path: Path | None, resume: bool,
) -> StageResult:
    input_hash = artifact_hash(payload)
    if resume and cache_path is not None and cache_path.exists():
        cached = read_json(cache_path)
        if cached.get("prompt_name") != prompt_name or cached.get("input_hash") != input_hash:
            raise ValueError(f"{prompt_name} stage cache does not match current input")
        artifact = cached.get("artifact")
        if not isinstance(artifact, dict):
            raise ValueError(f"{prompt_name} stage cache has no artifact")
        issues = validator(artifact)
        if issues:
            raise ValueError(
                f"{prompt_name} stage cache failed validation: {'; '.join(issues)}"
            )
        return StageResult(
            artifact=artifact,
            traces=_records(cached.get("traces")),
            initial_issues=[str(item) for item in cached.get("initial_issues", [])],
        )
    result = runner.run(prompt_name, payload, validator)
    if cache_path is not None:
        write_json(cache_path, {
            "prompt_name": prompt_name,
            "input_hash": input_hash,
            "artifact": result.artifact,
            "traces": result.traces,
            "initial_issues": result.initial_issues,
        })
    return result


def _stage_traces(results: list[StageResult]) -> list[dict[str, Any]]:
    return [trace for result in results for trace in result.traces]


def _cache(stage_cache_dir: str | Path | None, filename: str) -> Path | None:
    return Path(stage_cache_dir) / filename if stage_cache_dir is not None else None


def _required(row: dict[str, Any], key: str) -> str:
    value = str(row.get(key) or "")
    if not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
