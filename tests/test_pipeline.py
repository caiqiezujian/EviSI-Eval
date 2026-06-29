import json

import pytest

from evisi_eval.llm_provider import ScriptedLLMClient
from evisi_eval.pipeline import run_pipeline


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _primary_responses():
    return [
        {"sentences": [{"sentence_id": "S1", "sentence_text": "Mark left.", "anchor_ids": ["A1"]}], "anchors": [{"anchor_id": "A1", "sentence_id": "S1", "source_span": "Mark", "normalized_value": "Mark", "anchor_type": "PERSON", "role_hint": "participant", "attributes": {}, "importance": 3, "required": True, "confidence": 0.95}]},
        {"events": [{"event_id": "V1", "sentence_id": "S1", "evidence_spans": ["Mark left"], "canonical_meaning": "Mark left", "predicate": "leave", "arguments": [{"role": "agent", "anchor_id": "A1", "source_span": "Mark"}], "linked_anchor_ids": ["A1"], "attributes": {"polarity": "positive", "modality": "asserted", "direction": "exit", "scope": None, "tense_aspect": "past"}, "importance": 3, "required": True, "confidence": 0.95}], "relations": [], "allowed_omissions": []},
        {"target_units": [{"unit_id": "T1", "unit_text": "马克离开了。"}], "sentence_alignments": [{"source_sentence_id": "S1", "source_sentence_text": "Mark left.", "target_unit_ids": ["T1"], "target_spans": ["马克离开了。"], "alignment_type": "one_to_one", "group_id": None, "confidence": 0.98, "reason": "clear semantic correspondence"}], "unaligned_target_unit_ids": []},
        {"target_units": [{"unit_id": "T1", "unit_text": "马克离开了。"}], "target_anchors": [{"target_anchor_id": "TA1", "unit_id": "T1", "target_span": "马克", "normalized_value": "Mark", "anchor_type": "PERSON", "attributes": {}, "confidence": 0.95}], "target_events": [{"target_event_id": "TV1", "unit_ids": ["T1"], "evidence_spans": ["马克离开了"], "canonical_meaning": "Mark left", "predicate": "leave", "arguments": [{"role": "agent", "target_anchor_id": "TA1", "target_span": "马克"}], "attributes": {"polarity": "positive", "modality": "asserted", "direction": "exit", "scope": None, "tense_aspect": "past"}, "confidence": 0.95}], "target_relations": []},
        {"anchor_alignments": [{"anchor_id": "A1", "target_anchor_ids": ["TA1"], "target_unit_ids": ["T1"], "target_spans": ["马克"], "verdict": "equivalent", "confidence": 0.98, "reason": "translated name"}], "event_alignments": [{"event_id": "V1", "target_event_ids": ["TV1"], "target_unit_ids": ["T1"], "target_spans": ["马克离开了"], "verdict": "covered", "error_scope": "none", "attribute_errors": [], "confidence": 0.98, "reason": "event preserved"}], "relation_alignments": []},
        {"fluency_issues": [], "efficiency_issues": []},
    ]


def test_pipeline_runs_and_resume_is_hash_safe(tmp_path):
    samples = tmp_path / "samples.jsonl"
    outputs = tmp_path / "outputs.jsonl"
    _write_jsonl(samples, [{"sample_id": "s1", "transcript": "Mark left.", "src_lang": "en", "tgt_lang": "zh"}])
    _write_jsonl(outputs, [{"sample_id": "s1", "system_name": "system_a", "si_translation": "马克离开了。"}])
    primary = ScriptedLLMClient(_primary_responses())
    review = ScriptedLLMClient([])
    metrics = run_pipeline(str(samples), str(outputs), str(tmp_path / "results"), "run", primary_client=primary, review_client=review)
    assert metrics["num_results"] == 1
    assert metrics["average_score"] == 100.0
    assert (tmp_path / "results" / "run" / "report.html").exists()

    resumed = run_pipeline(
        str(samples), str(outputs), str(tmp_path / "results"), "run", resume=True,
        primary_client=ScriptedLLMClient([]), review_client=ScriptedLLMClient([]),
    )
    assert resumed["num_results"] == 1

    _write_jsonl(outputs, [{"sample_id": "s1", "system_name": "system_a", "si_translation": "马克没有离开。"}])
    with pytest.raises(ValueError, match="outputs_sha256"):
        run_pipeline(
            str(samples), str(outputs), str(tmp_path / "results"), "run", resume=True,
            primary_client=ScriptedLLMClient([]), review_client=ScriptedLLMClient([]),
        )
