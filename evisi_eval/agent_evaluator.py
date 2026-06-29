from __future__ import annotations

from typing import Any

from .llm_provider import LLMClient, LLMResponse


VERIFIER_PROMPT_VERSION = "dimension_verifiers_v1.1"
REVIEW_PROMPT_VERSION = "error_reviewer_v1.0"

FACT_SYSTEM_PROMPT = """You are the Fact Verification Agent in an auditable simultaneous-interpretation benchmark.
Compare every supplied fact with the anonymous final SI translation. Judge semantic equivalence, not surface-string identity. Accept transliteration, abbreviation, paraphrase, translated names, and domain-standard aliases when they identify the same value. Use the offline reference only as an aid; the source fact is authoritative.

IMPORTANT — occurrence-level verification: Each fact in the card is an OCCURRENCE anchored to a specific source sentence (sentence_id / sentence_text are provided). You must judge whether that entity is correctly conveyed in the translation AT THE CORRESPONDING SEMANTIC POSITION — i.e., the part of the translation that maps to the source sentence for that occurrence. The same entity appearing elsewhere in the translation does NOT count as coverage of this occurrence. A fact can be wrong in one sentence even if correctly conveyed in another.

Do not invent an alias merely because it looks similar. For required technical terms and acronyms, an unlisted truncation or expansion (for example POCT -> POC) is ambiguous unless the target context explicitly preserves the complete technical concept. A wrong participant role or named object is not an acceptable paraphrase.

Return {"verdicts":[...]} with exactly one result per fact_id. Fields: fact_id, verdict, target_span, target_context_span, normalized_target_value, confidence, reason. verdict must be exact, equivalent, incorrect, missing, or ambiguous. target_span and target_context_span must be copied verbatim from the SI translation or null. target_context_span must be the smallest target clause that corresponds to the source sentence and contains target_span. Use incorrect only when contradictory/different evidence is present; use missing only after checking the semantic position corresponding to the source sentence; use ambiguous when evidence is insufficient. Do not output scores, deductions, caps, or stylistic judgments. JSON only."""

PROPOSITION_SYSTEM_PROMPT = """You are the Core Proposition Verification Agent for final simultaneous-interpretation output.
For every proposition, decide whether the listener receives the same atomic event, action, state, conclusion, or recommendation. Simultaneous-interpretation compression is valid: shorter wording is compressed_covered when the complete core meaning remains. Evaluate the predicate and arguments while avoiding a second penalty for fact values listed in linked_facts; those values are handled by the fact agent.

compressed_covered cannot excuse an omitted independent argument, conclusion, condition, speaker stance, or participant role. Do not claim that omitted content is "implied by context" unless the target text itself entails it. A changed actor or role is at least partially_covered.

Return {"verdicts":[...]} with one result per prop_id. Fields: prop_id, verdict, target_span, error_scope, confidence, reason. verdict must be covered, compressed_covered, partially_covered, missing, contradicted, or ambiguous. error_scope must be none, predicate, linked_fact_only, or mixed. Use linked_fact_only when the predicate is preserved and the only problem is already represented by linked_facts. target_span must be verbatim SI translation text or null. Do not compare strings mechanically. Do not score. JSON only."""

RELATION_SYSTEM_PROMPT = """You are the Logical Relation Verification Agent for final simultaneous-interpretation output.
For every supplied relation, determine whether the target preserves the source link between the referenced propositions: cause, condition, contrast, concession, comparison, purpose, temporal order, exception, attribution, or enumeration. Ordinary conjunction is not enough evidence. A reversed condition, cause, comparison, or attribution must be labeled reversed.

Return {"verdicts":[...]} with one result per relation_id. Fields: relation_id, verdict, target_span, independent_relation_error, confidence, reason. verdict must be preserved, weakened, missing, reversed, or ambiguous. independent_relation_error is false when the apparent relation failure is only a consequence of an already reported proposition/fact error. target_span must be verbatim SI translation text or null. Do not score. JSON only."""

TARGET_SYSTEM_PROMPT = """You are the Target-language Comprehensibility Agent. Evaluate only whether the final SI translation is understandable as target-language speech/text. Do not penalize translation meaning errors handled by other agents. Do not reward literary polish and do not penalize reasonable SI compression.

Report only concrete issues from this closed list: grammar_error, sentence_fragment, source_language_residue, unnatural_collocation, repetitive_surface, unclear_reference, register_mismatch, unintelligible_segment. Return {"issues":[...]} where each issue has issue_id, error_type, target_span, severity, confidence, reason, listener_impact. severity must be minor, major, or critical. target_span must be copied verbatim from the SI translation. Return an empty issues array when no concrete problem exists. Do not score. JSON only."""

REVIEW_SYSTEM_PROMPT = """You are the Error Review Agent. Review each proposed local error independently. Your job is not to rescore the translation. Check whether the cited target evidence supports the proposed verdict and whether an acceptable translation variant was overlooked.

The offline translation is never evidence that the tested SI translation contains something. To mark a source-side missing/incorrect/contradicted candidate as invalid, counterevidence_span must quote verbatim text from the tested SI translation that preserves the item. Without such counterevidence, return uncertain or valid.

Return {"decisions":[...]} with exactly one decision per error_ref. Fields: error_ref, decision, resolved_verdict, counterevidence_span, confidence, reason. decision must be valid, invalid, or uncertain. For an ambiguous candidate, resolved_verdict may provide a valid dimension-specific verdict; otherwise use null. Mark invalid when the meaning is actually preserved or the evidence span is wrong. Mark uncertain when the supplied text cannot establish the error. Do not output scores or deductions. JSON only."""


def evaluate_with_agents(
    card: dict[str, Any],
    system_name: str,
    si_translation: str,
    primary_client: LLMClient,
    review_client: LLMClient | None = None,
) -> dict[str, Any]:
    translation = (si_translation or "").strip()
    if not translation:
        raise ValueError("si_translation must be non-empty")

    traces: list[dict[str, Any]] = []
    fact_verdicts = []
    scored_facts = [fact for fact in card.get("facts", []) if fact.get("is_score_anchor", True)]
    if scored_facts:
        fact_response = primary_client.generate_json(
            FACT_SYSTEM_PROMPT,
            {
                "task": "verify_facts",
                "transcript": card["transcript"],
                "offline_translation": card.get("offline_translation"),
                "facts": scored_facts,
                "terminology": card.get("terminology", []),
                "si_translation": translation,
                "tgt_lang": card.get("tgt_lang"),
            },
            task="verify_facts",
        )
        traces.append(_trace("verify_facts", fact_response))
        fact_verdicts = _normalize_verdicts(
            scored_facts, fact_response.data, "fact_id", "ambiguous", translation
        )

    prop_response = primary_client.generate_json(
        PROPOSITION_SYSTEM_PROMPT,
        {
            "task": "verify_propositions",
            "transcript": card["transcript"],
            "offline_translation": card.get("offline_translation"),
            "propositions": card.get("propositions", []),
            "fact_verdicts": [
                {"fact_id": item["fact_id"], "verdict": item["verdict"]} for item in fact_verdicts
            ],
            "allowed_omissions": card.get("allowed_omissions", []),
            "si_translation": translation,
            "tgt_lang": card.get("tgt_lang"),
        },
        task="verify_propositions",
    )
    traces.append(_trace("verify_propositions", prop_response))
    proposition_verdicts = _normalize_verdicts(
        card.get("propositions", []), prop_response.data, "prop_id", "ambiguous", translation
    )

    relation_verdicts = []
    if card.get("relations"):
        relation_response = primary_client.generate_json(
            RELATION_SYSTEM_PROMPT,
            {
                "task": "verify_relations",
                "transcript": card["transcript"],
                "relations": card.get("relations", []),
                "propositions": card.get("propositions", []),
                "proposition_verdicts": [
                    {"prop_id": item["prop_id"], "verdict": item["verdict"]}
                    for item in proposition_verdicts
                ],
                "si_translation": translation,
                "tgt_lang": card.get("tgt_lang"),
            },
            task="verify_relations",
        )
        traces.append(_trace("verify_relations", relation_response))
        relation_verdicts = _normalize_verdicts(
            card.get("relations", []), relation_response.data, "relation_id", "ambiguous", translation
        )

    target_response = primary_client.generate_json(
        TARGET_SYSTEM_PROMPT,
        {
            "task": "check_target_comprehensibility",
            "si_translation": translation,
            "tgt_lang": card.get("tgt_lang"),
        },
        task="check_target_comprehensibility",
    )
    traces.append(_trace("check_target_comprehensibility", target_response))
    target_issues = _normalize_target_issues(target_response.data, translation)

    candidate_errors = _candidate_errors(
        card, fact_verdicts, proposition_verdicts, relation_verdicts, target_issues
    )
    review_decisions: dict[str, dict[str, Any]] = {}
    if review_client is not None and candidate_errors:
        review_response = review_client.generate_json(
            REVIEW_SYSTEM_PROMPT,
            {
                "task": "review_candidate_errors",
                "transcript": card["transcript"],
                "offline_translation": card.get("offline_translation"),
                "si_translation": translation,
                "candidate_errors": candidate_errors,
            },
            task="review_candidate_errors",
        )
        traces.append(_trace("review_candidate_errors", review_response))
        review_decisions = _normalize_review_decisions(
            review_response.data, candidate_errors, translation
        )

    for group in (fact_verdicts, proposition_verdicts, relation_verdicts, target_issues):
        for verdict in group:
            error_ref = verdict.get("error_ref")
            if error_ref and error_ref in review_decisions:
                verdict["review"] = review_decisions[error_ref]
                resolved = review_decisions[error_ref].get("resolved_verdict")
                if verdict.get("verdict") == "ambiguous" and resolved:
                    verdict["verdict"] = _normalize_status(
                        _id_key_for_verdict(verdict), resolved, "ambiguous"
                    )
                    verdict["reason"] = (
                        f"Resolved by reviewer: {review_decisions[error_ref].get('reason')}"
                    )
            elif error_ref:
                verdict["review"] = {
                    "decision": "uncertain",
                    "confidence": 0.0,
                    "reason": "No review model was configured",
                }

    return {
        "sample_id": card["sample_id"],
        "system_name": system_name,
        "transcript": card["transcript"],
        "offline_translation": card.get("offline_translation"),
        "si_translation": translation,
        "evaluation_mode": "reference_assisted" if card.get("offline_translation") else "source_only",
        "card_hash": card.get("metadata", {}).get("card_hash"),
        "card_status": card.get("metadata", {}).get("card_status", "unknown"),
        "card": card,
        "fact_verdicts": fact_verdicts,
        "proposition_verdicts": proposition_verdicts,
        "relation_verdicts": relation_verdicts,
        "target_quality_issues": target_issues,
        "agent_trace": traces,
        "metadata": {
            "schema_version": "1.0.0",
            "verifier_prompt_version": VERIFIER_PROMPT_VERSION,
            "review_prompt_version": REVIEW_PROMPT_VERSION,
            "primary_provider": primary_client.provider_name,
            "primary_model": primary_client.model_name,
            "review_provider": review_client.provider_name if review_client else None,
            "review_model": review_client.model_name if review_client else None,
            "system_name_visible_to_verifiers": False,
            "system_asr_used": False,
        },
    }


def _normalize_verdicts(
    items: list[dict[str, Any]],
    response: dict[str, Any],
    id_key: str,
    default_verdict: str,
    translation: str,
) -> list[dict[str, Any]]:
    raw = response.get("verdicts")
    raw_items = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    by_id = {str(item.get(id_key)): item for item in raw_items if item.get(id_key)}
    normalized = []
    for source_item in items:
        item_id = str(source_item[id_key])
        verdict = dict(by_id.get(item_id) or {})
        status = _normalize_status(id_key, verdict.get("verdict"), default_verdict)
        target_span = _optional_string(verdict.get("target_span"))
        confidence = _confidence(verdict.get("confidence"), 0.0)
        reason = str(verdict.get("reason") or "Model omitted a valid structured verdict")
        if target_span is not None and target_span not in translation:
            status = "ambiguous"
            confidence = 0.0
            reason = "Rejected: target_span is not verbatim text from the SI translation"
            target_span = None
        target_context_span = _optional_string(verdict.get("target_context_span"))
        if target_context_span is not None and target_context_span not in translation:
            status = "ambiguous"
            confidence = 0.0
            reason = "Rejected: target_context_span is not verbatim text from the SI translation"
            target_context_span = None
        if target_span is not None and target_context_span is not None and target_span not in target_context_span:
            status = "ambiguous"
            confidence = 0.0
            reason = "Rejected: target_context_span does not contain target_span"
        normalized_item = {
            **source_item,
            "verdict": status,
            "target_span": target_span,
            "target_context_span": target_context_span,
            "confidence": confidence,
            "reason": reason,
        }
        if "normalized_target_value" in verdict:
            normalized_item["normalized_target_value"] = verdict.get("normalized_target_value")
        if id_key == "prop_id":
            scope = str(verdict.get("error_scope") or "none").strip().lower()
            normalized_item["error_scope"] = (
                scope if scope in {"none", "predicate", "linked_fact_only", "mixed"} else "none"
            )
        if id_key == "relation_id":
            normalized_item["independent_relation_error"] = bool(
                verdict.get("independent_relation_error", True)
            )
        if status not in {"exact", "equivalent", "covered", "compressed_covered", "preserved"}:
            normalized_item["error_ref"] = f"{id_key}:{item_id}"
        normalized.append(normalized_item)
    return normalized


def _normalize_target_issues(response: dict[str, Any], translation: str) -> list[dict[str, Any]]:
    allowed_types = {
        "grammar_error",
        "sentence_fragment",
        "source_language_residue",
        "unnatural_collocation",
        "repetitive_surface",
        "unclear_reference",
        "register_mismatch",
        "unintelligible_segment",
    }
    raw = response.get("issues")
    raw_items = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    issues = []
    for index, item in enumerate(raw_items, 1):
        error_type = str(item.get("error_type") or "").strip().lower()
        target_span = _optional_string(item.get("target_span"))
        if error_type not in allowed_types or not target_span or target_span not in translation:
            continue
        issue_id = str(item.get("issue_id") or f"tq_{index:03d}")
        issues.append(
            {
                "issue_id": issue_id,
                "error_type": error_type,
                "target_span": target_span,
                "severity": _severity(item.get("severity")),
                "confidence": _confidence(item.get("confidence"), 0.0),
                "reason": str(item.get("reason") or "Target-language issue"),
                "listener_impact": str(item.get("listener_impact") or "unspecified"),
                "error_ref": f"issue_id:{issue_id}",
            }
        )
    return issues


def _candidate_errors(
    card: dict[str, Any],
    facts: list[dict[str, Any]],
    propositions: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    target_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = []
    for dimension, values in (
        ("fact_accuracy", facts),
        ("core_proposition_coverage", propositions),
        ("logic_relation_preservation", relations),
        ("target_language_comprehensibility", target_issues),
    ):
        for value in values:
            if not value.get("error_ref"):
                continue
            candidates.append(
                {
                    "error_ref": value["error_ref"],
                    "dimension": dimension,
                    "item": value,
                    "forbidden_loss": _is_forbidden(card, value),
                }
            )
    return candidates


def _normalize_review_decisions(
    response: dict[str, Any], candidates: list[dict[str, Any]], translation: str
) -> dict[str, dict[str, Any]]:
    expected = {item["error_ref"] for item in candidates}
    dimensions = {item["error_ref"]: item["dimension"] for item in candidates}
    raw = response.get("decisions")
    raw_items = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    decisions = {}
    for item in raw_items:
        error_ref = str(item.get("error_ref") or "")
        if error_ref not in expected:
            continue
        decision = str(item.get("decision") or "uncertain").strip().lower()
        if decision not in {"valid", "invalid", "uncertain"}:
            decision = "uncertain"
        counterevidence = _optional_string(item.get("counterevidence_span"))
        if counterevidence is not None and counterevidence not in translation:
            counterevidence = None
        if (
            decision == "invalid"
            and dimensions[error_ref] != "target_language_comprehensibility"
            and counterevidence is None
        ):
            decision = "uncertain"
        decisions[error_ref] = {
            "decision": decision,
            "resolved_verdict": _optional_string(item.get("resolved_verdict")),
            "counterevidence_span": counterevidence,
            "confidence": _confidence(item.get("confidence"), 0.0),
            "reason": str(item.get("reason") or "No review reason supplied"),
        }
    for error_ref in expected - decisions.keys():
        decisions[error_ref] = {
            "decision": "uncertain",
            "resolved_verdict": None,
            "counterevidence_span": None,
            "confidence": 0.0,
            "reason": "Review model omitted this candidate error",
        }
    return decisions


def _is_forbidden(card: dict[str, Any], value: dict[str, Any]) -> bool:
    item_id = value.get("fact_id") or value.get("prop_id") or value.get("relation_id")
    return any(item.get("ref_id") == item_id for item in card.get("forbidden_losses", []))


def _trace(task: str, response: LLMResponse) -> dict[str, Any]:
    return {
        "task": task,
        "provider": response.provider,
        "model": response.model,
        "request_id": response.request_id,
        "usage": response.usage,
    }


def _confidence(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return round(min(1.0, max(0.0, parsed)), 4)


def _severity(value: Any) -> str:
    severity = str(value or "minor").strip().lower()
    return severity if severity in {"minor", "major", "critical"} else "minor"


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_status(id_key: str, value: Any, default: str) -> str:
    status = str(value or default).strip().lower()
    aliases = {
        "correct": {"fact_id": "equivalent", "prop_id": "covered", "relation_id": "preserved"},
        "partial": {"prop_id": "partially_covered", "relation_id": "weakened"},
    }
    status = aliases.get(status, {}).get(id_key, status)
    allowed = {
        "fact_id": {"exact", "equivalent", "incorrect", "missing", "ambiguous"},
        "prop_id": {"covered", "compressed_covered", "partially_covered", "missing", "contradicted", "ambiguous"},
        "relation_id": {"preserved", "weakened", "missing", "reversed", "ambiguous"},
    }
    return status if status in allowed[id_key] else "ambiguous"


def _id_key_for_verdict(verdict: dict[str, Any]) -> str:
    for key in ("fact_id", "prop_id", "relation_id"):
        if key in verdict:
            return key
    raise ValueError("Cannot resolve verdict item type")
