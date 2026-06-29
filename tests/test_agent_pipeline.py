import json

from evisi_eval.agent_aggregator import aggregate_agent_result
from evisi_eval.agent_card_builder import build_agent_card, normalize_card
from evisi_eval.agent_evaluator import evaluate_with_agents
from evisi_eval.agent_pipeline import run_agent_pipeline
from evisi_eval.io_utils import write_jsonl
from evisi_eval.llm_provider import ScriptedLLMClient, parse_json_object


def test_llm_agent_pipeline_is_blind_and_evidence_driven(tmp_path):
    samples = tmp_path / "samples.jsonl"
    outputs = tmp_path / "outputs.jsonl"
    write_jsonl(
        samples,
        [
            {
                "sample_id": "s1",
                "transcript": "Apple reported that revenue increased, but warned about margin risk.",
                "offline_translation": "苹果报告收入增长，但警告利润率风险。",
                "src_lang": "en",
                "tgt_lang": "zh",
                "domain": "finance",
            }
        ],
    )
    write_jsonl(
        outputs,
        [
            {
                "sample_id": "s1",
                "system_name": "secret-system-name",
                "si_translation": "谷歌表示收入下降，而且没有风险。",
                "system_asr": "must never be sent to a judge",
            }
        ],
    )

    primary = ScriptedLLMClient(
        [
            {
                "facts": [
                    {
                        "fact_id": "f_001",
                        "type": "entity",
                        "source_span": "Apple",
                        "canonical_value": "Apple",
                        "importance": 3,
                        "must_preserve": True,
                        "acceptable_variants": ["Apple", "苹果", "苹果公司"],
                        "notes": "speaker subject",
                        "extraction_confidence": 0.99,
                    }
                ],
                "propositions": [
                    {
                        "prop_id": "p_001",
                        "source_span": "revenue increased",
                        "canonical_meaning": "revenue increased",
                        "target_reference": "收入增长",
                        "importance": 3,
                        "required": True,
                        "linked_facts": [],
                        "notes": None,
                        "extraction_confidence": 0.98,
                    },
                    {
                        "prop_id": "p_002",
                        "source_span": "warned about margin risk",
                        "canonical_meaning": "the speaker warned about margin risk",
                        "target_reference": "警告利润率风险",
                        "importance": 2,
                        "required": True,
                        "linked_facts": [],
                        "notes": None,
                        "extraction_confidence": 0.96,
                    },
                ],
                "relations": [
                    {
                        "relation_id": "r_001",
                        "type": "contrast",
                        "source_cues": ["but"],
                        "head_prop_id": "p_001",
                        "dependent_prop_id": "p_002",
                        "canonical_meaning": "positive result contrasted with risk warning",
                        "importance": 2,
                        "extraction_confidence": 0.97,
                    }
                ],
                "terminology": [],
                "allowed_omissions": [],
                "forbidden_losses": [
                    {"kind": "fact", "ref_id": "f_001", "reason": "subject identity"},
                    {"kind": "proposition", "ref_id": "p_001", "reason": "core result"},
                ],
            },
            {
                "verdicts": [
                    {
                        "fact_id": "f_001",
                        "verdict": "incorrect",
                        "target_span": "谷歌",
                        "normalized_target_value": "Google",
                        "confidence": 0.99,
                        "reason": "Apple was replaced by Google",
                    }
                ]
            },
            {
                "verdicts": [
                    {
                        "prop_id": "p_001",
                        "verdict": "contradicted",
                        "target_span": "收入下降",
                        "confidence": 0.98,
                        "reason": "increase became decrease",
                    },
                    {
                        "prop_id": "p_002",
                        "verdict": "contradicted",
                        "target_span": "没有风险",
                        "confidence": 0.96,
                        "reason": "warning became denial of risk",
                    },
                ]
            },
            {
                "verdicts": [
                    {
                        "relation_id": "r_001",
                        "verdict": "reversed",
                        "target_span": "而且",
                        "confidence": 0.92,
                        "reason": "contrast became additive coordination",
                    }
                ]
            },
            {"issues": []},
        ]
    )
    reviewer = ScriptedLLMClient(
        [
            {
                "decisions": [
                    {"error_ref": "fact_id:f_001", "decision": "valid", "confidence": 0.99, "reason": "confirmed"},
                    {"error_ref": "prop_id:p_001", "decision": "valid", "confidence": 0.99, "reason": "confirmed"},
                    {"error_ref": "prop_id:p_002", "decision": "valid", "confidence": 0.98, "reason": "confirmed"},
                    {"error_ref": "relation_id:r_001", "decision": "valid", "confidence": 0.95, "reason": "confirmed"},
                ]
            }
        ],
        provider="review-fixture",
    )

    metrics = run_agent_pipeline(
        str(samples),
        str(outputs),
        output_dir=str(tmp_path / "results"),
        run_name="test",
        primary_client=primary,
        review_client=reviewer,
    )
    assert metrics["num_results"] == 1
    result_path = tmp_path / "results/test/evaluation_result/evisi_agent/results.jsonl"
    result = json.loads(result_path.read_text(encoding="utf-8").strip())
    assert result["final_score"] <= 55
    assert result["cap_triggered"] is True
    assert result["dimension_scores"]["fact_accuracy"]["score"] == 0
    assert result["metadata"]["system_asr_used"] is False
    assert (tmp_path / "results/test/evaluation_result/evisi_agent/report.html").exists()
    assert (tmp_path / "results/test/evaluation_result/evisi_agent/partial_results.jsonl").exists()

    all_payloads = json.dumps([call["payload"] for call in primary.calls], ensure_ascii=False)
    assert "secret-system-name" not in all_payloads
    assert "must never be sent to a judge" not in all_payloads

    resumed = run_agent_pipeline(
        str(samples),
        str(outputs),
        output_dir=str(tmp_path / "results"),
        run_name="test",
        primary_client=primary,
        review_client=reviewer,
        resume=True,
    )
    assert resumed["num_results"] == 1


def test_invalid_review_prevents_deduction():
    raw = {
        "sample_id": "s1",
        "system_name": "sys",
        "metadata": {},
        "fact_verdicts": [
            {
                "fact_id": "f1",
                "type": "entity",
                "source_span": "Apple",
                "importance": 3,
                "verdict": "incorrect",
                "target_span": "苹果",
                "confidence": 0.99,
                "reason": "candidate mismatch",
                "error_ref": "fact_id:f1",
                "review": {"decision": "invalid", "counterevidence_span": "苹果", "confidence": 0.99, "reason": "valid alias"},
            }
        ],
        "proposition_verdicts": [],
        "relation_verdicts": [],
        "target_quality_issues": [],
    }
    result = aggregate_agent_result(raw)
    assert result["dimension_scores"]["fact_accuracy"]["score"] == 40
    assert result["attributed_errors"] == []
    assert result["cap_triggered"] is False


def test_parse_json_object_accepts_fenced_json():
    assert parse_json_object('```json\n{"ok": true}\n```') == {"ok": True}


def test_linked_fact_only_proposition_is_not_double_penalized():
    raw = {
        "sample_id": "s1",
        "system_name": "sys",
        "metadata": {},
        "fact_verdicts": [],
        "proposition_verdicts": [
            {
                "prop_id": "p1",
                "source_span": "Apple reported growth",
                "importance": 3,
                "verdict": "partially_covered",
                "error_scope": "linked_fact_only",
                "target_span": "谷歌报告增长",
                "confidence": 0.99,
                "reason": "predicate preserved; only entity differs",
                "error_ref": "prop_id:p1",
                "review": {"decision": "valid", "confidence": 0.99, "reason": "fact error only"},
            }
        ],
        "relation_verdicts": [],
        "target_quality_issues": [],
    }
    result = aggregate_agent_result(raw)
    prop = result["proposition_verdicts"][0]
    assert prop["duplicate_suppressed"] is True
    assert prop["deduction"] == 0
    assert result["dimension_scores"]["core_proposition_coverage"]["score"] == 35


def test_occurrence_layout_preserves_importance_and_normalizes_sentences():
    transcript = "Mark answered. Mark left."
    raw = {
        "sentences": [
            {
                "sentence_id": "S1",
                "sentence_text": "Mark answered.",
                "entity_occurrences": [
                    {
                        "occurrence_id": "E1",
                        "sentence_id": "S1",
                        "sentence_text": "Mark answered.",
                        "entity_text": "Mark",
                        "normalized_entity": "Mark",
                        "entity_type": "PERSON",
                        "importance": "high",
                        "is_score_anchor": True,
                        "role_hint": "subject",
                        "extraction_reason": "subject identity",
                    }
                ],
            },
            {
                "sentence_id": "S2",
                "sentence_text": "Mark left.",
                "entity_occurrences": [
                    {
                        "occurrence_id": "E2",
                        "sentence_id": "S2",
                        "sentence_text": "Mark left.",
                        "entity_text": "Mark",
                        "normalized_entity": "Mark",
                        "entity_type": "PERSON",
                        "importance": "low",
                        "is_score_anchor": False,
                        "role_hint": "subject",
                        "extraction_reason": "background repeat",
                    }
                ],
            },
        ],
        "propositions": [
            {
                "prop_id": "p1",
                "source_span": "Mark answered.",
                "canonical_meaning": "Mark answered",
                "importance": 2,
                "required": True,
                "linked_entities": ["E1"],
                "extraction_confidence": 1.0,
            }
        ],
        "relations": [],
        "terminology": [],
        "allowed_omissions": [],
        "forbidden_losses": [],
    }
    card, issues = normalize_card(raw, {"sample_id": "s1", "transcript": transcript})
    assert issues == []
    assert [fact["importance_numeric"] for fact in card["facts"]] == [3, 1]
    assert [item["occurrence_id"] for item in card["entity_occurrences"]] == ["E1", "E2"]
    assert card["global_entity_inventory"][0]["occurrence_ids"] == ["E1", "E2"]


def test_occurrence_verifier_sends_only_score_anchors():
    card = {
        "sample_id": "s1",
        "transcript": "Mark answered. Mark left.",
        "offline_translation": "马克回答了。马克离开了。",
        "tgt_lang": "zh",
        "facts": [
            {"fact_id": "E1", "source_span": "Mark", "importance": "high", "importance_numeric": 3, "is_score_anchor": True},
            {"fact_id": "E2", "source_span": "Mark", "importance": "low", "importance_numeric": 1, "is_score_anchor": False},
        ],
        "propositions": [
            {"prop_id": "p1", "source_span": "Mark answered.", "canonical_meaning": "Mark answered", "importance": 2, "required": True}
        ],
        "relations": [],
        "terminology": [],
        "allowed_omissions": [],
        "metadata": {},
    }
    client = ScriptedLLMClient(
        [
            {"verdicts": [{"fact_id": "E1", "verdict": "equivalent", "target_span": "马克", "target_context_span": "马克回答了。", "confidence": 1.0, "reason": "matched"}]},
            {"verdicts": [{"prop_id": "p1", "verdict": "covered", "target_span": "马克回答了。", "error_scope": "none", "confidence": 1.0, "reason": "covered"}]},
            {"issues": []},
        ]
    )
    result = evaluate_with_agents(card, "hidden", "马克回答了。马克离开了。", client)
    assert [item["fact_id"] for item in result["fact_verdicts"]] == ["E1"]
    assert [item["fact_id"] for item in client.calls[0]["payload"]["facts"]] == ["E1"]


def test_semantic_importance_controls_fact_budget_and_criticality():
    raw = {
        "sample_id": "s1",
        "system_name": "sys",
        "metadata": {},
        "fact_verdicts": [
            {
                "fact_id": "E1",
                "type": "person",
                "source_span": "Mark",
                "importance": "high",
                "importance_numeric": 3,
                "verdict": "incorrect",
                "target_span": "约翰",
                "confidence": 1.0,
                "reason": "wrong person",
                "error_ref": "fact_id:E1",
                "review": {"decision": "valid", "confidence": 1.0, "reason": "confirmed"},
            },
            {
                "fact_id": "E2",
                "type": "key_concept",
                "source_span": "background",
                "importance": "low",
                "importance_numeric": 1,
                "verdict": "incorrect",
                "target_span": "背景",
                "confidence": 1.0,
                "reason": "minor mismatch",
                "error_ref": "fact_id:E2",
                "review": {"decision": "valid", "confidence": 1.0, "reason": "confirmed"},
            },
        ],
        "proposition_verdicts": [],
        "relation_verdicts": [],
        "target_quality_issues": [],
    }
    result = aggregate_agent_result(raw)
    facts = result["fact_verdicts"]
    assert facts[0]["item_budget"] == 30
    assert facts[0]["severity"] == "critical"
    assert facts[1]["item_budget"] == 10
    assert facts[1]["severity"] == "minor"
    assert result["score_cap"] == 60


def test_non_verbatim_occurrence_is_never_scored():
    transcript = "Round-robin um um load balancing scheme."
    raw = {
        "sentences": [
            {
                "sentence_id": "S1",
                "sentence_text": transcript,
                "entity_occurrences": [
                    {
                        "occurrence_id": "E1",
                        "sentence_id": "S1",
                        "sentence_text": transcript,
                        "entity_text": "Round-robin load balancing scheme",
                        "normalized_entity": "round-robin load balancing",
                        "entity_type": "TECH_TERM",
                        "importance": "high",
                        "is_score_anchor": True,
                        "role_hint": "term",
                        "extraction_reason": "core term",
                    }
                ],
            }
        ],
        "propositions": [],
        "relations": [],
        "terminology": [],
        "allowed_omissions": [],
        "forbidden_losses": [],
    }
    card, issues = normalize_card(raw, {"sample_id": "s1", "transcript": transcript})
    assert card["facts"] == []
    assert any("entity_text not found" in issue for issue in issues)


def test_card_builder_repairs_non_verbatim_occurrence():
    transcript = "Round-robin um um load balancing scheme."
    base_sentence = {
        "sentence_id": "S1",
        "sentence_text": transcript,
    }
    initial = {
        "sentences": [
            {
                **base_sentence,
                "entity_occurrences": [
                    {
                        "occurrence_id": "E1",
                        **base_sentence,
                        "entity_text": "Round-robin load balancing scheme",
                        "normalized_entity": "round-robin load balancing",
                        "entity_type": "TECH_TERM",
                        "importance": "high",
                        "is_score_anchor": True,
                        "role_hint": "term",
                        "extraction_reason": "core term",
                    }
                ],
            }
        ],
        "propositions": [],
        "relations": [],
        "terminology": [],
        "allowed_omissions": [],
        "forbidden_losses": [],
    }
    repaired = {
        **initial,
        "sentences": [
            {
                **base_sentence,
                "entity_occurrences": [
                    {
                        "occurrence_id": "E1",
                        **base_sentence,
                        "entity_text": "Round-robin",
                        "normalized_entity": "round-robin load balancing",
                        "entity_type": "TECH_TERM",
                        "importance": "high",
                        "is_score_anchor": True,
                        "role_hint": "term",
                        "extraction_reason": "core term",
                    }
                ],
            }
        ],
    }
    client = ScriptedLLMClient([initial, repaired])
    card = build_agent_card({"sample_id": "s1", "transcript": transcript}, client)
    assert card["facts"][0]["source_span"] == "Round-robin"
    assert card["metadata"]["repair_attempted"] is True
    assert card["metadata"]["review_required"] is True  # fallback proposition still needs review
    assert len(client.calls) == 2
