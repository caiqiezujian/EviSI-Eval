from __future__ import annotations

import json

from evisi_eval.io_utils import read_jsonl
from evisi_eval.llm_provider import ScriptedLLMClient
from evisi_eval.prompt_loader import load_prompt
from evisi_eval.v06_pipeline import check_v06_input_files, run_v06_pipeline
from evisi_eval.v06_validation import calculate_v06_scores, validate_anchor_projections


def _write_jsonl(path, rows) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def source_segment_response() -> dict:
    return {"source_segments": [{
        "segment_id": "G1",
        "source_segment": "Company received 250,000 US dollars.",
    }]}


def source_anchor_response() -> dict:
    return {"source_anchors": [{
        "segment_id": "G1", "source_anchor_id": "SA1", "anchor_type": "A-QNT",
        "anchor_text": "250,000 US dollars", "normalized_value": "250000 USD",
        "components": {"value": "250000", "currency": "USD"},
        "evidence_span": "250,000 US dollars", "importance": 3,
    }]}


def source_event_response() -> dict:
    return {"source_events": [{
        "segment_id": "G1", "source_event_id": "SE1", "event_type": "E-ACT",
        "evidence_spans": ["Company received 250,000 US dollars"],
        "predicate_span": "received", "core_predicate": "receive",
        "arguments": [
            {"role": "agent", "surface_span": "Company", "source_anchor_ids": []},
            {"role": "value", "surface_span": "250,000 US dollars", "source_anchor_ids": ["SA1"]},
        ],
        "operators": {
            "negation": False, "modality": None, "direction": "gain",
            "polarity": "positive", "stance": None,
        },
        "canonical_proposition": "company receives a monetary value", "importance": 3,
    }]}


def source_relation_response() -> dict:
    return {"source_relations": []}


def alignment_response(translation: str) -> dict:
    return {"target_units": [{
        "target_unit_id": "T1", "source_segment_ids": ["G1"],
        "target_text": translation, "alignment_status": "aligned", "reason": "内容对应",
    }]}


def hard_requirement() -> dict:
    return {
        "required": True, "requirement_type": "exact_value_unit",
        "required_target_form": None, "required_semantics": [],
        "basis": "intrinsic_exactness", "reason": "金额和币种必须精确",
    }


def event_requirement() -> dict:
    return {
        "required": False, "requirement_type": None,
        "required_target_form": None, "required_semantics": [],
        "basis": None, "reason": "",
    }


def reference_anchor_response() -> dict:
    return {"anchor_projections": [{
        "projection_id": "AP1", "source_anchor_id": "SA1",
        "target_unit_ids": ["T1"], "target_spans": ["25万美元"],
        "target_meaning": "250000 USD",
        "component_results": [
            {"component": "value", "source_value": "250000", "target_value": "250000", "status": "preserved", "target_span": "25万"},
            {"component": "currency", "source_value": "USD", "target_value": "USD", "status": "preserved", "target_span": "美元"},
        ],
        "mapping_status": "equivalent", "hard_requirement": hard_requirement(),
        "hard_requirement_satisfied": None, "confidence": 0.99, "reason": "金额一致",
    }], "target_additions": []}


def reference_event_response() -> dict:
    return {"event_projections": [{
        "projection_id": "EP1", "source_event_id": "SE1",
        "target_unit_ids": ["T1"], "target_spans": ["公司收到了25万美元"],
        "target_meaning": "公司获得一笔金额",
        "target_event_structure": {
            "core_predicate": "获得", "predicate_span": "收到了", "arguments": [],
            "operators": {"negation": False, "modality": None, "direction": "gain", "polarity": "positive", "stance": None},
            "canonical_proposition": "公司获得一笔金额",
        },
        "predicate_status": "preserved", "argument_status": "preserved",
        "operator_status": "preserved", "mapping_status": "equivalent",
        "hard_requirement": event_requirement(), "hard_requirement_satisfied": None,
        "confidence": 0.98, "reason": "核心事件一致",
    }], "target_additions": []}


def empty_relations() -> dict:
    return {"relation_projections": [], "target_additions": []}


def si_anchor_response() -> dict:
    return {"anchor_projections": [{
        "projection_id": "AP1", "source_anchor_id": "SA1",
        "target_unit_ids": ["T1"], "target_spans": ["25万元"],
        "target_meaning": "250000 CNY",
        "component_results": [
            {"component": "value", "source_value": "250000", "target_value": "250000", "status": "preserved", "target_span": "25万"},
            {"component": "currency", "source_value": "USD", "target_value": "CNY", "status": "contradicted", "target_span": "元"},
        ],
        "mapping_status": "contradiction", "hard_requirement": hard_requirement(),
        "hard_requirement_satisfied": False, "confidence": 0.99, "reason": "币种冲突",
    }], "target_additions": []}


def si_event_response() -> dict:
    row = reference_event_response()["event_projections"][0]
    row = {**row, "target_spans": ["公司收到了25万元"], "hard_requirement_satisfied": None,
           "reason": "谓词与角色正确；币种错误归 Anchor"}
    return {"event_projections": [row], "target_additions": []}


def responses() -> list[dict]:
    return [
        source_segment_response(), source_anchor_response(), source_event_response(),
        source_relation_response(), alignment_response("公司收到了25万美元。"),
        reference_anchor_response(), reference_event_response(), empty_relations(),
        alignment_response("公司收到了25万元。"), si_anchor_response(),
        si_event_response(), empty_relations(),
        {"fluency_issues": [], "fluency_assessment": "通顺。"},
        {"si_expression_issues": [], "si_expression_assessment": "简洁。"},
    ]


def test_v06_pipeline_projects_reference_and_si_from_source(tmp_path) -> None:
    samples = tmp_path / "samples.jsonl"
    outputs = tmp_path / "outputs.jsonl"
    _write_jsonl(samples, [{
        "sample_id": "s1", "source_text": "Company received 250,000 US dollars.",
        "reference_translation": "公司收到了25万美元。", "reference_type": "human_gold",
        "src_lang": "en", "tgt_lang": "zh",
    }])
    _write_jsonl(outputs, [{
        "sample_id": "s1", "system_name": "system_a",
        "si_translation": "公司收到了25万元。",
    }])
    client = ScriptedLLMClient(responses(), provider="scripted", model="v06-fixture")

    metrics = run_v06_pipeline(
        str(samples), str(outputs), output_dir=str(tmp_path / "results"),
        run_name="run", client=client,
    )

    assert metrics["num_results"] == 1
    assert metrics["num_failures"] == 0
    result = read_jsonl(tmp_path / "results" / "run" / "score" / "final_results_v06.jsonl")[0]
    context = read_jsonl(
        tmp_path / "results" / "run" / "context" / "evaluation_context_cards.jsonl"
    )[0]
    si_card = read_jsonl(
        tmp_path / "results" / "run" / "target" / "si_projection_cards.jsonl"
    )[0]
    assert result["anchor_projections"][0]["mapping_status"] == "contradiction"
    assert result["event_projections"][0]["mapping_status"] == "equivalent"
    assert result["dimension_scores"]["anchor_fidelity"] == 0.0
    assert result["dimension_scores"]["event_fidelity"] == 100.0
    assert result["final_score"] == 61.11
    assert context["metadata"]["constructed_without_llm"] is True
    assert si_card["reference_card_hash"] == result["reference_card_hash"]
    assert si_card["evaluation_context_hash"] == result["evaluation_context_hash"]
    anchor_decision = result["score_diagnostics"]["anchor_fidelity"]["item_decisions"][0]
    assert anchor_decision["component_statuses"] == {
        "value": "preserved", "currency": "contradicted",
    }
    assert anchor_decision["weighted_contribution"] == 0.0
    assert [call["task"] for call in client.calls] == [
        "v06_source_segment_agent", "v06_source_anchor_agent", "v06_source_event_agent",
        "v06_source_relation_agent", "v06_target_alignment_agent",
        "v06_reference_anchor_projection_agent", "v06_reference_event_projection_agent",
        "v06_reference_relation_projection_agent", "v06_target_alignment_agent",
        "v06_si_anchor_projection_agent", "v06_si_event_projection_agent",
        "v06_si_relation_projection_agent", "fluency_agent", "si_expression_agent",
    ]

    resumed = ScriptedLLMClient([], provider="scripted", model="v06-fixture")
    resumed_metrics = run_v06_pipeline(
        str(samples), str(outputs), output_dir=str(tmp_path / "results"),
        run_name="run", client=resumed, resume=True,
    )
    assert resumed_metrics["num_results"] == 1
    assert resumed.calls == []


def test_v06_relation_blocked_by_event_is_not_double_penalized() -> None:
    source_card = {
        "source_anchors": [],
        "source_events": [{"source_event_id": "SE1", "importance": 3}],
        "source_relations": [{"source_relation_id": "SR1", "importance": 3}],
    }
    si_card = {
        "anchor_projections": [],
        "event_projections": [{"source_event_id": "SE1", "mapping_status": "missing"}],
        "relation_projections": [{
            "source_relation_id": "SR1", "mapping_status": "not_scored",
            "dependency_status": "blocked_by_event",
        }],
    }
    score = calculate_v06_scores(source_card, si_card, [], [])
    assert score["dimension_scores"]["event_fidelity"] == 0.0
    assert score["dimension_scores"]["relation_fidelity"] is None
    assert score["score_diagnostics"]["relation_fidelity"]["blocked_items"] == 1


def test_v06_prompts_forbid_reference_string_matching_and_form_lists() -> None:
    anchor_prompt = load_prompt("v06_si_anchor_projection_agent")
    assert "SI 与 Reference 不同绝不自动构成错误" in anchor_prompt
    assert "禁止生成 accepted_forms" in anchor_prompt
    event_prompt = load_prompt("v06_si_event_projection_agent")
    assert "Anchor 错误不能重复归 Event" in event_prompt


def test_anchor_projection_cannot_change_frozen_source_component() -> None:
    source = source_anchor_response()["source_anchors"]
    artifact = si_anchor_response()
    artifact["anchor_projections"][0]["component_results"][0]["source_value"] = "25000"
    issues = validate_anchor_projections(
        artifact, source, alignment_response("公司收到了25万元。")["target_units"],
        si_mode=True,
    )
    assert any("changed source component value" in issue for issue in issues)


def test_check_v06_input_accepts_existing_aliases_without_llm(tmp_path) -> None:
    samples = tmp_path / "samples.jsonl"
    outputs = tmp_path / "outputs.jsonl"
    _write_jsonl(samples, [{
        "sample_id": "s1", "transcript": "Source.",
        "offline_translation": "参考译文。", "src_lang": "en", "tgt_lang": "zh",
    }])
    _write_jsonl(outputs, [{
        "sample_id": "s1", "system_name": "system_a",
        "si_translation": "同传译文。", "system_asr": "ignored",
    }])
    summary = check_v06_input_files(str(samples), str(outputs))
    assert summary["valid"] is True
    assert summary["num_samples"] == 1
    assert summary["num_outputs"] == 1
    assert summary["normalization"]["ignored_fields"] == ["system_asr"]
