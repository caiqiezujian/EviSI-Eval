import json

from evisi_eval.agent_aggregator import aggregate_agent_result
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
