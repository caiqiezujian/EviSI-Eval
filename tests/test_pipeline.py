import json

from evisi_eval.llm_provider import ScriptedLLMClient
from evisi_eval.pipeline import run_pipeline


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


def _responses():
    return [_source_response(), _target_response(), _main_response()]


def test_pipeline_writes_cards_and_hides_system_name(tmp_path):
    """Integration test: run_pipeline uses AgentLoop, writes cards, hides system name."""
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
        [
            {
                "sample_id": "s1",
                "system_name": "system_a",
                "si_translation": "马克离开了。",
            }
        ],
    )
    client = ScriptedLLMClient(_responses())
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
    # v0.4 file layout: source_cards + target_eval_cards + final_results
    assert (run_dir / "source/source_cards.jsonl").exists()
    assert (run_dir / "target/target_eval_cards.jsonl").exists()
    assert (run_dir / "score/score_06_final_results.jsonl").exists()
    assert (run_dir / "report.html").exists()
    assert (run_dir / "agent_trace.jsonl").exists()

    # System name isolation: real name never reaches agent payloads
    assert all(
        call["payload"].get("system_name") != "system_a"
        for call in client.calls
        if "system_name" in call["payload"]
    )

    # Reference translation isolation: never reaches agent payloads
    for call in client.calls:
        assert "reference_translation" not in call["payload"], (
            f"reference_translation leaked into {call['task']} payload"
        )
