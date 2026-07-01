"""EviSI-Eval shared agent infrastructure — Runner + Delivery agents.

  - Runner: LLM call → validate → repair (MAX_REPAIR_ATTEMPTS=2) → fallback → ValueError
  - FluencyAgent / SIExpressionAgent: v0.7 Phases 13-14
  - StageResult: dataclass for stage outputs
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from .llm_provider import LLMClient, LLMResponse
from .prompt_loader import load_prompt

MAX_REPAIR_ATTEMPTS = 2


# ── shared helpers ─────────────────────────────────────────────────────

def validate_delivery_artifact(
    artifact: dict[str, Any],
    translation: str,
    issues_key: str,
    assessment_key: str,
    prefix: str,
) -> list[str]:
    """Validate fluency / si_expression artifacts.

    Checks: assessment is non-empty, each issue has issue_id/issue_type/reason/severity,
    target_spans are verbatim substrings, no duplicate spans, severity is valid.
    """
    SEVERITIES = {"minor", "moderate", "major", "critical"}
    issues_list: list[str] = []

    assessment = str(artifact.get(assessment_key, ""))
    if not assessment.strip():
        issues_list.append(f"{prefix}: {assessment_key} is empty")

    rows = [row for row in artifact.get(issues_key, []) if isinstance(row, dict)]
    _sequential_ids(rows, "issue_id", prefix, issues_key, issues_list)
    seen_spans: set[str] = set()
    for row in rows:
        iid = str(row.get("issue_id", ""))
        span = str(row.get("target_span", ""))
        if span and span not in translation:
            issues_list.append(f"issue {iid} has non-verbatim target_span")
        if not str(row.get("issue_type", "")).strip():
            issues_list.append(f"issue {iid} is missing issue_type")
        if not str(row.get("reason", "")).strip():
            issues_list.append(f"issue {iid} is missing reason")
        if row.get("severity") not in SEVERITIES:
            issues_list.append(f"issue {iid} has unsupported severity")
        if span:
            if span in seen_spans:
                issues_list.append(f"issue {iid} target_span already penalized")
            seen_spans.add(span)

    return issues_list


def _sequential_ids(
    rows: list[dict[str, Any]],
    id_field: str,
    prefix: str,
    parent_key: str,
    issues: list[str],
) -> None:
    expected = 1
    for row in rows:
        actual = str(row.get(id_field, ""))
        expected_id = f"{prefix}{expected}"
        if actual != expected_id:
            issues.append(
                f"{parent_key} {id_field} expected {expected_id}, got {actual}"
            )
        expected += 1


# ── core types ─────────────────────────────────────────────────────────

@dataclass
class StageResult:
    artifact: dict[str, Any]
    traces: list[dict[str, Any]]
    initial_issues: list[str]


# ── Runner ─────────────────────────────────────────────────────────────

class Runner:
    """Run one semantic agent and allow up to MAX_REPAIR_ATTEMPTS structure-only repairs."""

    def __init__(self, client: LLMClient):
        self.client = client

    def run(
        self,
        prompt_name: str,
        payload: dict[str, Any],
        validator: Callable[[dict[str, Any]], list[str]],
        fallback: Callable[[], dict[str, Any]] | None = None,
    ) -> StageResult:
        started = time.perf_counter()
        response = self.client.generate_json(load_prompt(prompt_name), payload, task=prompt_name)
        elapsed = time.perf_counter() - started
        artifact = _canonicalize(response.data, payload)
        traces = [_trace(prompt_name, response, elapsed)]
        initial_issues = validator(artifact)
        issues = list(initial_issues)
        for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
            if not issues:
                break
            started = time.perf_counter()
            repair = self.client.generate_json(
                load_prompt("schema_repair"),
                {
                    "stage_name": prompt_name,
                    "stage_input": payload,
                    "validation_issues": issues,
                    "repair_attempt": attempt,
                    "json_to_repair": artifact,
                },
                task=f"repair_{prompt_name}",
            )
            traces.append(_trace(
                f"repair_{prompt_name}", repair, time.perf_counter() - started
            ))
            artifact = _canonicalize(repair.data, payload)
            issues = validator(artifact)
        if issues and fallback is not None:
            artifact = _canonicalize(fallback(), payload)
            issues = validator(artifact)
            traces.append(_local_trace(f"fallback_{prompt_name}"))
        if issues:
            raise ValueError(f"{prompt_name} failed validation: {'; '.join(issues)}")
        return StageResult(artifact, traces, initial_issues)


# ── Delivery agents ────────────────────────────────────────────────────

class FluencyAgent:
    """Evaluate SI fluency — v0.7 Phase 13."""

    def __init__(self, client: LLMClient):
        self.runner = Runner(client)

    def evaluate(self, sample_id: str, translation: str) -> StageResult:
        payload = {
            "sample_id": sample_id,
            "system_name": "anonymous_system",
            "si_translation": translation,
        }
        return self.runner.run(
            "fluency_agent",
            payload,
            lambda artifact: validate_delivery_artifact(
                artifact, translation, "fluency_issues", "fluency_assessment", "F"
            ),
        )


class SIExpressionAgent:
    """Evaluate SI expression quality — v0.7 Phase 14."""

    def __init__(self, client: LLMClient):
        self.runner = Runner(client)

    def evaluate(self, source_card: dict[str, Any], translation: str) -> StageResult:
        payload = {
            "sample_id": source_card["sample_id"],
            "system_name": "anonymous_system",
            "source_text": source_card["source_text"],
            "si_translation": translation,
        }
        return self.runner.run(
            "si_expression_agent",
            payload,
            lambda artifact: validate_delivery_artifact(
                artifact, translation, "si_expression_issues", "si_expression_assessment", "X"
            ),
        )


# ── internal helpers ───────────────────────────────────────────────────

def _canonicalize(raw: Any, payload: dict[str, Any]) -> dict[str, Any]:
    artifact = dict(raw) if isinstance(raw, dict) else {}
    for key in ("sample_id", "system_name"):
        if key in payload:
            artifact[key] = payload[key]
    return artifact


def _required(row: dict[str, Any], key: str) -> str:
    value = str(row.get(key) or "")
    if not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _trace(task: str, response: LLMResponse, elapsed_seconds: float | None = None) -> dict[str, Any]:
    return {
        "task": task,
        "provider": response.provider,
        "model": response.model,
        "request_id": response.request_id,
        "usage": response.usage,
        "elapsed_seconds": round(elapsed_seconds, 3) if elapsed_seconds is not None else None,
    }


def _local_trace(task: str) -> dict[str, Any]:
    return {"task": task, "provider": "deterministic", "model": "local", "request_id": None, "usage": {}}
