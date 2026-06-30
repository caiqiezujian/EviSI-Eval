from __future__ import annotations

import json

from evisi_eval.io_utils import read_jsonl
from evisi_eval.agents import SourceCardAgent
from evisi_eval.llm_provider import ScriptedLLMClient
from evisi_eval.pipeline import compute_metrics, run_pipeline
from tests.test_agents import (
    alignment_response,
    expression_response,
    fluency_response,
    judgement_response,
    source_response,
    summary_response,
    target_response,
)


def _write_jsonl(path, rows) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _per_output_responses() -> list[dict]:
    return [
        alignment_response(), target_response(), fluency_response(), expression_response(),
        judgement_response(), judgement_response(), summary_response(),
    ]


def test_pipeline_builds_one_frozen_source_card_for_multiple_systems(tmp_path) -> None:
    samples = tmp_path / "samples.jsonl"
    outputs = tmp_path / "outputs.jsonl"
    _write_jsonl(samples, [{
        "sample_id": "s1", "source_text": "Mark left.",
        "reference_translation": "马克离开了。", "src_lang": "en", "tgt_lang": "zh",
    }])
    _write_jsonl(outputs, [
        {"sample_id": "s1", "system_name": "system_a", "si_translation": "马克离开了。"},
        {"sample_id": "s1", "system_name": "system_b", "si_translation": "马克离开了。"},
    ])
    client = ScriptedLLMClient(
        [source_response(), *_per_output_responses(), *_per_output_responses()],
        provider="scripted", model="fixture-v05",
    )

    metrics = run_pipeline(
        str(samples), str(outputs), output_dir=str(tmp_path / "results"),
        run_name="run", primary_client=client,
    )

    assert metrics["num_results"] == 2
    assert metrics["num_failures"] == 0
    assert sum(call["task"] == "source_evidence_agent" for call in client.calls) == 1
    results = read_jsonl(tmp_path / "results" / "run" / "score" / "score_06_final_results.jsonl")
    assert len({row["source_card_hash"] for row in results}) == 1
    assert {row["system_name"] for row in results} == {"system_a", "system_b"}
    assert (tmp_path / "results" / "run" / "report.html").exists()
    assert client.responses == []


def test_resume_reuses_frozen_cards_and_completed_results(tmp_path) -> None:
    samples = tmp_path / "samples.jsonl"
    outputs = tmp_path / "outputs.jsonl"
    _write_jsonl(samples, [{"sample_id": "s1", "source_text": "Mark left."}])
    _write_jsonl(outputs, [{
        "sample_id": "s1", "system_name": "system_a", "si_translation": "马克离开了。"
    }])
    first = ScriptedLLMClient(
        [source_response(), *_per_output_responses()], provider="scripted", model="fixture-v05"
    )
    kwargs = {
        "samples_path": str(samples), "outputs_path": str(outputs),
        "output_dir": str(tmp_path / "results"), "run_name": "run",
    }
    run_pipeline(**kwargs, primary_client=first)

    resumed = ScriptedLLMClient([], provider="scripted", model="fixture-v05")
    metrics = run_pipeline(**kwargs, primary_client=resumed, resume=True)

    assert metrics["num_results"] == 1
    assert resumed.calls == []


def test_metrics_exclude_provisional_and_unscored_results_from_official_average() -> None:
    dimensions = {
        "anchor_fidelity": 80.0, "event_fidelity": 80.0,
        "relation_fidelity": 80.0, "fluency": 80.0, "si_expression": 80.0,
    }
    results = [
        {"system_name": "system_a", "final_score": 80.0, "score_status": "final",
         "dimension_scores": dimensions},
        {"system_name": "system_a", "final_score": 100.0,
         "score_status": "provisional_review_required", "dimension_scores": dimensions},
        {"system_name": "system_a", "final_score": None,
         "score_status": "provisional_no_decisions",
         "dimension_scores": {**dimensions, "anchor_fidelity": None}},
    ]

    metrics = compute_metrics(results)
    system = metrics["systems"]["system_a"]
    assert metrics["average_score"] == 80.0
    assert metrics["provisional_average_score"] == 100.0
    assert metrics["diagnostic_average_score_including_provisional"] == 90.0
    assert metrics["num_final_results"] == 1
    assert metrics["num_provisional_results"] == 2
    assert metrics["num_unscored_results"] == 1
    assert system["average_score"] == 80.0
    assert system["provisional_average_score"] == 100.0
    assert system["unscored_results"] == 1


def test_metrics_exclude_not_applicable_content_dimensions() -> None:
    base = {
        "anchor_fidelity": 90.0, "event_fidelity": 90.0,
        "fluency": 90.0, "si_expression": 90.0,
    }
    results = [
        {"system_name": "system_a", "final_score": 90.0, "score_status": "final",
         "dimension_scores": {**base, "relation_fidelity": 100.0},
         "score_diagnostics": {"relation_fidelity": {"applicable": False}}},
        {"system_name": "system_a", "final_score": 80.0, "score_status": "final",
         "dimension_scores": {**base, "relation_fidelity": 50.0},
         "score_diagnostics": {"relation_fidelity": {"applicable": True}}},
    ]

    metrics = compute_metrics(results)
    assert metrics["systems"]["system_a"]["dimension_scores"]["relation_fidelity"] == 50.0


def test_pipeline_reuses_validated_external_source_card_cache(tmp_path) -> None:
    samples = tmp_path / "samples.jsonl"
    outputs = tmp_path / "outputs.jsonl"
    cache = tmp_path / "source_cards.jsonl"
    sample_row = {"sample_id": "s1", "source_text": "Mark left."}
    _write_jsonl(samples, [sample_row])
    _write_jsonl(outputs, [{
        "sample_id": "s1", "system_name": "system_a", "si_translation": "马克离开了。"
    }])
    source_client = ScriptedLLMClient([source_response()])
    card, _ = SourceCardAgent(source_client).build(sample_row)
    _write_jsonl(cache, [card])
    evaluation_client = ScriptedLLMClient(
        _per_output_responses(), provider="scripted", model="fixture-v05"
    )

    metrics = run_pipeline(
        str(samples), str(outputs), output_dir=str(tmp_path / "results"), run_name="cached",
        primary_client=evaluation_client, source_card_cache_path=str(cache),
    )

    assert metrics["num_results"] == 1
    assert all(call["task"] != "source_evidence_agent" for call in evaluation_client.calls)
    manifest = json.loads((tmp_path / "results" / "cached" / "run_manifest.json").read_text("utf-8"))
    assert manifest["source_card_cache_sha256"]


def test_pipeline_reuses_validated_external_target_card_cache(tmp_path) -> None:
    samples = tmp_path / "samples.jsonl"
    outputs = tmp_path / "outputs.jsonl"
    source_cache = tmp_path / "source_cards.jsonl"
    target_cache = tmp_path / "target_cards.jsonl"
    sample_row = {"sample_id": "s1", "source_text": "Mark left."}
    _write_jsonl(samples, [sample_row])
    _write_jsonl(outputs, [{
        "sample_id": "s1", "system_name": "system_a", "si_translation": "马克离开了。"
    }])
    source_client = ScriptedLLMClient([source_response()])
    source_card, _ = SourceCardAgent(source_client).build(sample_row)
    _write_jsonl(source_cache, [source_card])
    target_card = {
        "eval_units": alignment_response()["eval_units"],
        **target_response(),
        **fluency_response(),
        **expression_response(),
        "sample_id": "s1", "system_name": "system_a", "si_translation": "马克离开了。",
        "metadata": {},
    }
    _write_jsonl(target_cache, [target_card])
    evaluation_client = ScriptedLLMClient([
        judgement_response(), judgement_response(), summary_response()
    ], provider="scripted", model="fixture-v05")

    metrics = run_pipeline(
        str(samples), str(outputs), output_dir=str(tmp_path / "results"), run_name="cached",
        primary_client=evaluation_client, source_card_cache_path=str(source_cache),
        target_card_cache_path=str(target_cache),
    )

    assert metrics["num_results"] == 1
    assert [call["task"] for call in evaluation_client.calls] == [
        "primary_judge_agent", "reviewer_agent", "summary_agent"
    ]
    manifest = json.loads((tmp_path / "results" / "cached" / "run_manifest.json").read_text("utf-8"))
    assert manifest["target_card_cache_sha256"]
