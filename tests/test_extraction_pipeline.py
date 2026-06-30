from __future__ import annotations

import json

import pytest

from evisi_eval.extraction_pipeline import run_extraction_pipeline
from evisi_eval.io_utils import read_jsonl
from evisi_eval.llm_provider import ScriptedLLMClient
from tests.test_agents import alignment_response, source_response, target_response


def _write_jsonl(path, rows) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_extraction_pipeline_runs_only_three_semantic_stages_and_resumes(tmp_path) -> None:
    samples = tmp_path / "samples.jsonl"
    outputs = tmp_path / "outputs.jsonl"
    _write_jsonl(samples, [{"sample_id": "s1", "source_text": "Mark left."}])
    _write_jsonl(outputs, [{
        "sample_id": "s1", "system_name": "system_a", "si_translation": "马克离开了。"
    }])
    client = ScriptedLLMClient(
        [source_response(), alignment_response(), target_response()],
        provider="scripted", model="semantic-fixture",
    )
    kwargs = {
        "samples_path": str(samples), "outputs_path": str(outputs),
        "output_dir": str(tmp_path / "results"), "run_name": "extract",
    }

    summary = run_extraction_pipeline(**kwargs, client=client)
    assert summary["source_cards"] == 1
    assert summary["alignments"] == 1
    assert summary["target_cards"] == 1
    assert summary["failures"] == 0
    assert [call["task"] for call in client.calls] == [
        "source_evidence_agent", "alignment_agent", "target_evidence_agent"
    ]
    target_cards = read_jsonl(
        tmp_path / "results" / "extract" / "target" / "target_semantic_cards.jsonl"
    )
    assert "fluency_issues" not in target_cards[0]
    assert "score" not in json.dumps(target_cards[0])

    resumed = ScriptedLLMClient([], provider="scripted", model="semantic-fixture")
    resumed_summary = run_extraction_pipeline(**kwargs, client=resumed, resume=True)
    assert resumed_summary["target_cards"] == 1
    assert resumed.calls == []


def test_extraction_resume_rejects_artifacts_without_manifest(tmp_path) -> None:
    samples = tmp_path / "samples.jsonl"
    outputs = tmp_path / "outputs.jsonl"
    _write_jsonl(samples, [{"sample_id": "s1", "source_text": "Mark left."}])
    _write_jsonl(outputs, [{
        "sample_id": "s1", "system_name": "system_a", "si_translation": "马克离开了。"
    }])
    run_dir = tmp_path / "results" / "legacy"
    (run_dir / "source").mkdir(parents=True)
    _write_jsonl(run_dir / "source" / "source_cards.jsonl", [{"sample_id": "s1"}])

    with pytest.raises(ValueError, match="without extraction_manifest"):
        run_extraction_pipeline(
            samples_path=str(samples), outputs_path=str(outputs),
            output_dir=str(tmp_path / "results"), run_name="legacy", resume=True,
            client=ScriptedLLMClient([], provider="scripted", model="semantic-fixture"),
        )


def test_extraction_resume_revalidates_cached_semantics(tmp_path) -> None:
    samples = tmp_path / "samples.jsonl"
    outputs = tmp_path / "outputs.jsonl"
    _write_jsonl(samples, [{"sample_id": "s1", "source_text": "Mark left."}])
    _write_jsonl(outputs, [{
        "sample_id": "s1", "system_name": "system_a", "si_translation": "马克离开了。"
    }])
    client = ScriptedLLMClient(
        [source_response(), alignment_response(), target_response()],
        provider="scripted", model="semantic-fixture",
    )
    kwargs = {
        "samples_path": str(samples), "outputs_path": str(outputs),
        "output_dir": str(tmp_path / "results"), "run_name": "extract",
    }
    run_extraction_pipeline(**kwargs, client=client)
    target_path = tmp_path / "results" / "extract" / "target" / "target_semantic_cards.jsonl"
    target_card = read_jsonl(target_path)[0]
    target_card["target_relations"] = [{
        "target_relation_id": "TR1",
        "relation_type": "temporal_sequence",
        "eval_unit_ids": ["E1"],
        "relation_text": "invented legacy relation",
        "relation_meaning": "invented legacy relation",
        "evidence_spans": ["马克离开了。"],
        "related_target_event_ids": ["TE1"],
    }]
    _write_jsonl(target_path, [target_card])

    with pytest.raises(ValueError, match="failed current protocol"):
        run_extraction_pipeline(
            **kwargs, resume=True,
            client=ScriptedLLMClient([], provider="scripted", model="semantic-fixture"),
        )
