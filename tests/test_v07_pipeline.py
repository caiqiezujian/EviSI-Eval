"""End-to-end smoke test for the v0.7 joint-card + positional SI matching pipeline.

Uses ScriptedLLMClient (no API keys) to feed 14 pre-baked JSON responses through
the full pipeline and assert the structural + scoring invariants.
"""

from __future__ import annotations

import json

import pytest

from evisi_eval.llm_provider import ScriptedLLMClient
from evisi_eval.v07_pipeline import run_v07_pipeline


# ── Fixture: a tiny 1-sample, 1-system fixture with lossless content ──────

SAMPLE_SOURCE = (
    "The company announced a new product."
    " The product uses neural networks for translation."
)
SAMPLE_REFERENCE = (
    "公司发布了一款新产品。"
    "该产品使用神经网络进行翻译。"
)
SAMPLE_SI = "公司宣布推出新产品。该产品利用神经网络做翻译。"

SAMPLE = {
    "sample_id": "s1",
    "source_text": SAMPLE_SOURCE,
    "reference_translation": SAMPLE_REFERENCE,
    "src_lang": "en",
    "tgt_lang": "zh",
    "domain": "tech",
}

OUTPUT = {
    "sample_id": "s1",
    "system_name": "systemA",
    "si_translation": SAMPLE_SI,
}


# ── Fixture: 14 scripted LLM responses ────────────────────────────────────
# Phases 1-8 build the Joint Card; phases 9-14 match one SI system.

SCRIPTED_RESPONSES = [
    # Phase 1 — Source Segments (must concatenate to SAMPLE_SOURCE exactly)
    {
        "sample_id": "s1",
        "source_segments": [
            {"seg_id": "S1", "source_text": "The company announced a new product."},
            {"seg_id": "S2", "source_text": " The product uses neural networks for translation."},
        ],
    },
    # Phase 2 — Source Anchors
    {
        "sample_id": "s1",
        "source_anchors": [
            {
                "anchor_id": "S1_A1", "seg_id": "S1",
                "type": "entity", "text": "The company",
                "evidence": "The company", "importance": 2,
            },
            {
                "anchor_id": "S1_A2", "seg_id": "S1",
                "type": "term", "text": "new product",
                "evidence": "a new product", "importance": 2,
            },
            {
                "anchor_id": "S2_A1", "seg_id": "S2",
                "type": "term", "text": "neural networks",
                "evidence": "neural networks", "importance": 3,
            },
        ],
    },
    # Phase 3 — Source Events
    {
        "sample_id": "s1",
        "source_events": [
            {
                "event_id": "S1_E1", "seg_id": "S1",
                "type": "action",
                "summary": "company announces new product",
                "evidence": "The company announced a new product.",
                "importance": 3,
            },
            {
                "event_id": "S2_E1", "seg_id": "S2",
                "type": "state",
                "summary": "product uses neural networks",
                "evidence": "The product uses neural networks for translation.",
                "importance": 3,
            },
        ],
    },
    # Phase 4 — Source Relations
    {
        "sample_id": "s1",
        "source_relations": [
            {
                "relation_id": "R1", "type": "temporal_sequence",
                "summary": "product launch precedes capability description",
                "source_event_ids": ["S1_E1", "S2_E1"],
                "evidence": "The company announced a new product. The product uses neural networks for translation.",
                "importance": 2,
            },
        ],
    },
    # Phase 5 — Reference Align (must concatenate to SAMPLE_REFERENCE exactly)
    {
        "sample_id": "s1",
        "reference_segments": [
            {"seg_id": "S1", "reference_text": "公司发布了一款新产品。"},
            {"seg_id": "S2", "reference_text": "该产品使用神经网络进行翻译。"},
        ],
    },
    # Phase 6 — Reference Anchors (positional, count matches source)
    {
        "sample_id": "s1",
        "reference_anchors": [
            {"anchor_id": "S1_A1", "seg_id": "S1", "type": "entity",
             "text": "公司", "evidence": "公司", "importance": 2},
            {"anchor_id": "S1_A2", "seg_id": "S1", "type": "term",
             "text": "新产品", "evidence": "新产品", "importance": 2},
            {"anchor_id": "S2_A1", "seg_id": "S2", "type": "term",
             "text": "神经网络", "evidence": "神经网络", "importance": 3},
        ],
    },
    # Phase 7 — Reference Events (positional, count matches source)
    {
        "sample_id": "s1",
        "reference_events": [
            {"event_id": "S1_E1", "seg_id": "S1", "type": "action",
             "summary": "公司发布新产品", "evidence": "公司发布了一款新产品。", "importance": 3},
            {"event_id": "S2_E1", "seg_id": "S2", "type": "state",
             "summary": "产品使用神经网络", "evidence": "该产品使用神经网络进行翻译。", "importance": 3},
        ],
    },
    # Phase 8 — Reference Relations (positional, count matches source)
    {
        "sample_id": "s1",
        "reference_relations": [
            {"relation_id": "R1", "preserved": True,
             "summary": "时间顺序保留", "importance": 2},
        ],
    },
    # Phase 9 — SI Align
    {
        "sample_id": "s1",
        "system_name": "systemA",
        "si_segments": [
            {"seg_id": "S1", "si_text": "公司宣布推出新产品。"},
            {"seg_id": "S2", "si_text": "该产品利用神经网络做翻译。"},
        ],
    },
    # Phase 10 — SI Anchor Match (positional, count matches joint_anchors)
    {
        "sample_id": "s1",
        "system_name": "systemA",
        "anchor_matches": [
            {"anchor_id": "S1_A1", "match": "equivalent",
             "si_text": "公司", "si_evidence": "公司", "brief": "公司↔公司"},
            {"anchor_id": "S1_A2", "match": "equivalent",
             "si_text": "新产品", "si_evidence": "新产品", "brief": "新产品↔新产品"},
            {"anchor_id": "S2_A1", "match": "equivalent",
             "si_text": "神经网络", "si_evidence": "神经网络", "brief": "神经网络↔神经网络"},
        ],
    },
    # Phase 11 — SI Event Match (positional, count matches joint_events)
    {
        "sample_id": "s1",
        "system_name": "systemA",
        "event_matches": [
            {"event_id": "S1_E1", "match": "equivalent",
             "si_summary": "公司宣布新产品", "si_evidence": "公司宣布推出新产品。",
             "brief": "announce vs 宣布"},
            {"event_id": "S2_E1", "match": "equivalent",
             "si_summary": "产品使用神经网络", "si_evidence": "该产品利用神经网络做翻译。",
             "brief": "use vs 利用"},
        ],
    },
    # Phase 12 — SI Relation Match (positional, count matches joint_relations)
    {
        "sample_id": "s1",
        "system_name": "systemA",
        "relation_matches": [
            {"relation_id": "R1", "match": "equivalent",
             "brief": "temporal order preserved"},
        ],
    },
    # Phase 13 — Fluency (delivery issues)
    {
        "sample_id": "s1",
        "system_name": "systemA",
        "fluency_assessment": "整体流畅，无明显语法错误。",
        "fluency_issues": [],
    },
    # Phase 14 — SI Expression
    {
        "sample_id": "s1",
        "system_name": "systemA",
        "si_expression_assessment": "同传表达自然，节奏合理。",
        "si_expression_issues": [],
    },
]


def _write_inputs(tmp_path):
    samples_path = tmp_path / "samples.jsonl"
    outputs_path = tmp_path / "outputs.jsonl"
    samples_path.write_text(json.dumps(SAMPLE, ensure_ascii=False) + "\n", encoding="utf-8")
    outputs_path.write_text(json.dumps(OUTPUT, ensure_ascii=False) + "\n", encoding="utf-8")
    return samples_path, outputs_path


def test_v07_pipeline_runs_end_to_end(tmp_path):
    samples_path, outputs_path = _write_inputs(tmp_path)
    client = ScriptedLLMClient(SCRIPTED_RESPONSES)

    metrics = run_v07_pipeline(
        samples_path=str(samples_path),
        outputs_path=str(outputs_path),
        output_dir=str(tmp_path),
        run_name="smoke",
        client=client,
    )

    # All 14 scripted responses consumed (no leftover)
    assert client.responses == [], f"leftover scripted responses: {len(client.responses)}"
    assert metrics["num_results"] == 1
    assert metrics["num_failures"] == 0

    # Output structure
    results_file = tmp_path / "smoke" / "score" / "final_results_v07.jsonl"
    assert results_file.exists()
    result = json.loads(results_file.read_text(encoding="utf-8").strip())

    # Score is computed
    assert result["final_score"] is not None
    assert 0 <= result["final_score"] <= 100
    assert result["score_status"] == "final"

    # All 5 dimensions present
    assert set(result["dimension_scores"].keys()) == {
        "anchor_fidelity", "event_fidelity", "relation_fidelity",
        "fluency", "si_expression",
    }

    # All anchor / event / relation matches landed equivalent → fidelity ≈ 100
    assert result["dimension_scores"]["anchor_fidelity"] == 100.0
    assert result["dimension_scores"]["event_fidelity"] == 100.0
    assert result["dimension_scores"]["relation_fidelity"] == 100.0
    assert result["dimension_scores"]["fluency"] == 100.0
    assert result["dimension_scores"]["si_expression"] == 100.0


def test_v07_pipeline_produces_frozen_joint_card(tmp_path):
    samples_path, outputs_path = _write_inputs(tmp_path)
    client = ScriptedLLMClient(SCRIPTED_RESPONSES)

    run_v07_pipeline(
        samples_path=str(samples_path),
        outputs_path=str(outputs_path),
        output_dir=str(tmp_path),
        run_name="smoke",
        client=client,
    )

    joint_file = tmp_path / "smoke" / "joint" / "joint_cards_v07.jsonl"
    assert joint_file.exists()
    card = json.loads(joint_file.read_text(encoding="utf-8").strip())

    # Frozen card has content hash
    assert "metadata" in card
    assert card["metadata"]["protocol_version"] == "evisi_eval_v0.7"
    assert card["metadata"]["joint_card_hash"]

    # Per-segment merged view preserves source / reference text + counts
    assert len(card["segments"]) == 2
    s1 = card["segments"][0]
    assert s1["seg_id"] == "S1"
    assert s1["source_text"] == "The company announced a new product."
    assert s1["reference_text"] == "公司发布了一款新产品。"
    assert len(s1["anchors"]) == 2
    assert len(s1["events"]) == 1

    s2 = card["segments"][1]
    assert s2["seg_id"] == "S2"
    assert len(s2["anchors"]) == 1
    assert len(s2["events"]) == 1

    # Flat views are convenience aliases
    assert len(card["flat_anchors"]) == 3
    assert len(card["flat_events"]) == 2
    assert len(card["flat_relations"]) == 1


def test_v07_pipeline_handles_partial_match(tmp_path):
    """When some matches are partial/contradiction, scoring reflects it."""
    samples_path, outputs_path = _write_inputs(tmp_path)

    responses = list(SCRIPTED_RESPONSES)
    # Phase 10: change one anchor to partial
    responses[9]["anchor_matches"] = [
        {"anchor_id": "S1_A1", "match": "equivalent",
         "si_text": "公司", "si_evidence": "公司", "brief": "ok"},
        {"anchor_id": "S1_A2", "match": "partial",
         "si_text": "新商品", "si_evidence": "新产品", "brief": "近义"},
        {"anchor_id": "S2_A1", "match": "missing",
         "si_text": "", "si_evidence": "", "brief": "丢失"},
    ]

    client = ScriptedLLMClient(responses)
    metrics = run_v07_pipeline(
        samples_path=str(samples_path),
        outputs_path=str(outputs_path),
        output_dir=str(tmp_path),
        run_name="smoke",
        client=client,
    )
    assert metrics["num_failures"] == 0

    result = json.loads(
        (tmp_path / "smoke" / "score" / "final_results_v07.jsonl")
        .read_text(encoding="utf-8").strip()
    )

    # Anchor weights: SA1=2, SA2=2, SA3=3 → total 7
    # Earned: SA1 equiv (1.0 × 2) + SA2 partial (0.5 × 2) + SA3 missing (0 × 3) = 3
    # Anchor score = 3 / 7 × 100 ≈ 42.86
    assert result["dimension_scores"]["anchor_fidelity"] == pytest.approx(42.86, abs=0.01)


def test_v07_pipeline_fails_when_input_invalid(tmp_path):
    """Empty source_text raises immediately, no LLM calls."""
    samples_path = tmp_path / "bad_samples.jsonl"
    outputs_path = tmp_path / "outputs.jsonl"
    samples_path.write_text(
        json.dumps({
            "sample_id": "s1", "source_text": "", "reference_translation": "x",
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    outputs_path.write_text(
        json.dumps(OUTPUT, ensure_ascii=False) + "\n", encoding="utf-8",
    )

    client = ScriptedLLMClient(list(SCRIPTED_RESPONSES))
    with pytest.raises(ValueError, match="non-empty source_text"):
        run_v07_pipeline(
            samples_path=str(samples_path),
            outputs_path=str(outputs_path),
            output_dir=str(tmp_path),
            run_name="smoke",
            client=client,
        )
    # No LLM calls should have been made
    assert client.calls == []