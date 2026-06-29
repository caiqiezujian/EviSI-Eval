"""Tests for the v0.4 agent-based evaluation architecture."""

import json

from evisi_eval.agents import AgentLoop
from evisi_eval.llm_provider import ScriptedLLMClient


def _write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _source_response():
    return {
        "sample_id": "s1",
        "source_units": [
            {"source_unit_id": "S1", "source_unit": "Mark left."}
        ],
        "source_anchors": [
            {
                "source_unit_id": "S1",
                "source_anchor_id": "SA1",
                "anchor_text": "Mark",
                "normalized_meaning": "Mark",
                "evidence_span": "Mark",
            }
        ],
        "source_events": [
            {
                "source_unit_id": "S1",
                "source_event_id": "SE1",
                "event_text": "Mark left",
                "canonical_meaning": "Mark left",
                "evidence_span": "Mark left",
            }
        ],
        "source_relations": [],
    }


def _target_response():
    return {
        "sample_id": "s1",
        "system_name": "anonymous_system",
        "eval_units": [
            {
                "eval_unit_id": "E1",
                "source_unit_ids": ["S1"],
                "target_unit": "马克离开了。",
                "alignment_status": "aligned",
                "reason": "direct correspondence",
            }
        ],
        "target_anchors": [
            {
                "eval_unit_id": "E1",
                "target_anchor_id": "TA1",
                "anchor_text": "马克",
                "normalized_meaning": "Mark",
                "evidence_span": "马克",
            }
        ],
        "target_events": [
            {
                "eval_unit_id": "E1",
                "target_event_id": "TE1",
                "event_text": "马克离开了",
                "canonical_meaning": "Mark left",
                "evidence_span": "马克离开了",
            }
        ],
        "target_relations": [],
        "fluency_issues": [],
        "fluency_assessment": "译文清楚自然。",
        "si_expression_issues": [],
        "si_expression_assessment": "表达简洁有效。",
    }


def _main_response():
    return {
        "sample_id": "s1",
        "system_name": "anonymous_system",
        "anchor_judgements": [
            {
                "anchor_judgement_id": "AJ1",
                "eval_unit_id": "E1",
                "source_anchor_id": "SA1",
                "source_anchor": "Mark",
                "target_match": "马克",
                "target_anchor_ids": ["TA1"],
                "verdict": "correct",
                "explanation": "人名准确传达。",
            }
        ],
        "anchor_fidelity_assessment": "全部 anchor 正确。",
        "event_judgements": [
            {
                "event_judgement_id": "EJ1",
                "eval_unit_id": "E1",
                "source_event_id": "SE1",
                "source_event": "Mark left",
                "target_match": "马克离开了",
                "target_event_ids": ["TE1"],
                "verdict": "correct",
                "explanation": "事件完整保留。",
            }
        ],
        "event_fidelity_assessment": "全部 event 正确。",
        "relation_judgements": [],
        "relation_fidelity_assessment": "源文无 relation。",
        "global_fidelity_review": {
            "delayed_expression_notes": [],
            "consistency_notes": [],
            "possible_duplicate_errors": [],
            "missed_global_issues": [],
            "misleading_addition_notes": [],
            "overall_fidelity_comment": "全文一致。",
        },
        "dimension_scores": {
            "anchor_fidelity": 100,
            "event_fidelity": 100,
            "relation_fidelity": 100,
            "fluency": 100,
            "si_expression": 100,
        },
        "dimension_score_explanations": {
            "anchor_fidelity": "1 correct。",
            "event_fidelity": "1 correct。",
            "relation_fidelity": "无适用项目。",
            "fluency": "0 issues。",
            "si_expression": "0 issues。",
        },
        "dimension_weights": {
            "anchor_fidelity": 30,
            "event_fidelity": 25,
            "relation_fidelity": 20,
            "fluency": 15,
            "si_expression": 10,
        },
        "final_score": 100.0,
        "score_summary": {
            "overall_judgement": "准确、流畅。",
            "main_strengths": ["内容完整"],
            "main_errors": [],
            "uncertain_points": [],
        },
        "reanalysis_request": None,
    }


# ── Tests ──


def test_agent_loop_end_to_end(tmp_path):
    """Full agent loop produces correct final result with perfect score."""
    client = ScriptedLLMClient(
        [_source_response(), _target_response(), _main_response()]
    )
    loop = AgentLoop(client)

    sample = {
        "sample_id": "s1",
        "source_text": "Mark left.",
        "reference_translation": "马克离开了。",
        "src_lang": "en",
        "tgt_lang": "zh",
    }
    output = {
        "sample_id": "s1",
        "system_name": "system_a",
        "si_translation": "马克离开了。",
    }

    result, artifacts = loop.run(sample, output)

    assert result["sample_id"] == "s1"
    assert result["system_name"] == "system_a"
    assert result["final_score"] == 100.0
    assert result["dimension_scores"]["anchor_fidelity"] == 100
    assert result["dimension_scores"]["event_fidelity"] == 100
    assert result["dimension_scores"]["relation_fidelity"] == 100

    # Source card was built
    assert "source_cards" in artifacts
    assert artifacts["source_cards"]["source_units"][0]["source_unit"] == "Mark left."
    assert len(artifacts["source_cards"]["source_anchors"]) == 1

    # Target card was built
    assert "target_eval_cards" in artifacts
    assert artifacts["target_eval_cards"]["eval_units"][0]["target_unit"] == "马克离开了。"

    # Agent trace was recorded
    trace = result["metadata"]["agent_trace"]
    tasks = [t["task"] for t in trace]
    assert "source_worker" in tasks
    assert "target_worker" in tasks
    assert "main_agent" in tasks


def test_system_name_isolation(tmp_path):
    """Real system name never reaches any agent payload."""
    client = ScriptedLLMClient(
        [_source_response(), _target_response(), _main_response()]
    )
    loop = AgentLoop(client)

    sample = {
        "sample_id": "s1",
        "source_text": "Mark left.",
        "src_lang": "en",
        "tgt_lang": "zh",
    }
    output = {
        "sample_id": "s1",
        "system_name": "RealSystem42",
        "si_translation": "马克离开了。",
    }

    loop.run(sample, output)

    # Every agent call must NOT contain the real system name
    for call in client.calls:
        payload_str = json.dumps(call["payload"], ensure_ascii=False)
        assert "RealSystem42" not in payload_str, (
            f"System name leaked into {call['task']} payload"
        )


def test_reference_translation_isolation(tmp_path):
    """Reference translation never reaches agent payloads."""
    client = ScriptedLLMClient(
        [_source_response(), _target_response(), _main_response()]
    )
    loop = AgentLoop(client)

    sample = {
        "sample_id": "s1",
        "source_text": "Mark left.",
        "reference_translation": "马克离开了。",
        "src_lang": "en",
        "tgt_lang": "zh",
    }
    output = {
        "sample_id": "s1",
        "system_name": "system_a",
        "si_translation": "马克离开了。",
    }

    loop.run(sample, output)

    for call in client.calls:
        payload_str = json.dumps(call["payload"], ensure_ascii=False)
        # reference_translation should only appear in source_card metadata,
        # not in any agent payload
        if call["task"] in ("source_worker", "target_worker", "main_agent"):
            assert "reference_translation" not in call["payload"], (
                f"reference_translation leaked into {call['task']} payload"
            )


def test_source_worker_sees_only_source(tmp_path):
    """SourceWorker payload contains source text but never si_translation."""
    client = ScriptedLLMClient(
        [_source_response(), _target_response(), _main_response()]
    )
    loop = AgentLoop(client)

    sample = {
        "sample_id": "s1",
        "source_text": "Mark left.",
        "src_lang": "en",
        "tgt_lang": "zh",
    }
    output = {
        "sample_id": "s1",
        "system_name": "system_a",
        "si_translation": "马克离开了。",
    }

    loop.run(sample, output)

    source_call = client.calls[0]
    assert source_call["task"] == "source_worker"
    assert "source_text" in source_call["payload"]
    assert "si_translation" not in source_call["payload"]
    assert "source_anchors" not in source_call["payload"]  # no prior analysis


def test_target_worker_sees_no_source_analysis(tmp_path):
    """TargetWorker receives source_units (id+text) but never source analysis results."""
    client = ScriptedLLMClient(
        [_source_response(), _target_response(), _main_response()]
    )
    loop = AgentLoop(client)

    sample = {
        "sample_id": "s1",
        "source_text": "Mark left.",
        "src_lang": "en",
        "tgt_lang": "zh",
    }
    output = {
        "sample_id": "s1",
        "system_name": "system_a",
        "si_translation": "马克离开了。",
    }

    loop.run(sample, output)

    target_call = client.calls[1]
    assert target_call["task"] == "target_worker"
    # Should have source_units for alignment
    assert "source_units" in target_call["payload"]
    # But NOT source anchors, events, or relations
    payload_str = json.dumps(target_call["payload"], ensure_ascii=False)
    assert "source_anchor" not in payload_str
    assert "source_event" not in payload_str
    assert "source_relation" not in payload_str
    # Should have si_translation
    assert "si_translation" in target_call["payload"]


def test_main_agent_sees_no_raw_text(tmp_path):
    """MainAgent sees structured data but never raw source_text or si_translation."""
    client = ScriptedLLMClient(
        [_source_response(), _target_response(), _main_response()]
    )
    loop = AgentLoop(client)

    sample = {
        "sample_id": "s1",
        "source_text": "Mark left.",
        "src_lang": "en",
        "tgt_lang": "zh",
    }
    output = {
        "sample_id": "s1",
        "system_name": "system_a",
        "si_translation": "马克离开了。",
    }

    loop.run(sample, output)

    main_call = client.calls[2]
    assert main_call["task"] == "main_agent"
    payload_str = json.dumps(main_call["payload"], ensure_ascii=False)
    # MainAgent receives source_card and target_eval_card (structured)
    assert "source_card" in main_call["payload"]
    assert "target_eval_card" in main_call["payload"]
    # But NOT raw text
    assert "source_text" not in main_call["payload"]
    assert "si_translation" not in main_call["payload"]


def test_reanalysis_flow(tmp_path):
    """MainAgent can request reanalysis from a worker."""
    # First MainAgent response: requests reanalysis
    main_with_reanalysis = {
        **_main_response(),
        "reanalysis_request": {
            "target": "target_worker",
            "reason": "Missing target anchor for Mark",
            "focus": "E1",
            "instructions": "Re-check E1 for the anchor 'Mark'",
        },
    }
    # Final MainAgent response: no reanalysis needed
    main_final = _main_response()

    # Need 5 responses: source, target, main(reanalysis), target(reanalysis), main(final)
    responses = [
        _source_response(),
        _target_response(),
        main_with_reanalysis,
        _target_response(),  # re-analyzed target
        main_final,
    ]
    client = ScriptedLLMClient(responses)
    loop = AgentLoop(client)

    sample = {
        "sample_id": "s1",
        "source_text": "Mark left.",
        "src_lang": "en",
        "tgt_lang": "zh",
    }
    output = {
        "sample_id": "s1",
        "system_name": "system_a",
        "si_translation": "马克离开了。",
    }

    result, artifacts = loop.run(sample, output)

    # Should have completed successfully
    assert result["final_score"] == 100.0
    # Should have made 5 calls total
    assert len(client.calls) == 5
    # Third call was the reanalysis-requesting main_agent
    assert client.calls[2]["task"] == "main_agent"
    # Fourth call was the re-analysis target_worker
    assert client.calls[3]["task"] == "target_worker"
    # The re-analysis call should have focus info
    assert "focus" in client.calls[3]["payload"]
    assert client.calls[3]["payload"]["focus"]["reason"] == "Missing target anchor for Mark"


def test_pipeline_with_agents(tmp_path):
    """Integration test: run_pipeline uses AgentLoop under the hood."""
    from evisi_eval.pipeline import run_pipeline

    samples = tmp_path / "samples.jsonl"
    outputs = tmp_path / "outputs.jsonl"
    _write_jsonl(
        samples,
        [
            {
                "sample_id": "s1",
                "source_text": "Mark left.",
                "reference_translation": "马克离开了。",
                "src_lang": "en",
                "tgt_lang": "zh",
            }
        ],
    )
    _write_jsonl(
        outputs,
        [{"sample_id": "s1", "system_name": "system_a", "si_translation": "马克离开了。"}],
    )

    client = ScriptedLLMClient(
        [_source_response(), _target_response(), _main_response()]
    )
    metrics = run_pipeline(
        str(samples),
        str(outputs),
        str(tmp_path / "results"),
        "run",
        client=client,
    )

    assert metrics["num_results"] == 1
    assert metrics["average_score"] == 100.0

    run_dir = tmp_path / "results" / "run"
    assert (run_dir / "source/source_cards.jsonl").exists()
    assert (run_dir / "target/target_eval_cards.jsonl").exists()
    assert (run_dir / "score/score_06_final_results.jsonl").exists()
    assert (run_dir / "report.html").exists()
    assert (run_dir / "agent_trace.jsonl").exists()
