from evisi_eval.card_builder import build_source_card
from evisi_eval.llm_provider import ScriptedLLMClient
from evisi_eval.validation import validate_source_card


def test_source_card_builds_anchors_events_and_relations():
    client = ScriptedLLMClient(
        [
            {
                "sentences": [
                    {"sentence_id": "S1", "sentence_text": "Mark invested 20 million dollars.", "anchor_ids": ["A1", "A2"]}
                ],
                "anchors": [
                    {"anchor_id": "A1", "sentence_id": "S1", "source_span": "Mark", "normalized_value": "Mark", "anchor_type": "PERSON", "role_hint": "participant", "attributes": {}, "importance": 3, "required": True, "confidence": 0.95},
                    {"anchor_id": "A2", "sentence_id": "S1", "source_span": "20 million dollars", "normalized_value": "USD 20000000", "anchor_type": "MONEY", "role_hint": "quantity", "attributes": {"value": "20000000", "unit": "USD"}, "importance": 3, "required": True, "confidence": 0.94},
                ],
            },
            {
                "events": [
                    {"event_id": "V1", "sentence_id": "S1", "evidence_spans": ["Mark invested 20 million dollars"], "canonical_meaning": "Mark invested USD 20 million", "predicate": "invest", "arguments": [{"role": "agent", "anchor_id": "A1", "source_span": "Mark"}, {"role": "quantity", "anchor_id": "A2", "source_span": "20 million dollars"}], "linked_anchor_ids": ["A1", "A2"], "attributes": {"polarity": "positive", "modality": "asserted", "direction": None, "scope": None, "tense_aspect": "past"}, "importance": 3, "required": True, "confidence": 0.96}
                ],
                "relations": [],
                "allowed_omissions": [],
            },
        ]
    )
    card = build_source_card(
        {"sample_id": "s1", "transcript": "Mark invested 20 million dollars.", "src_lang": "en", "tgt_lang": "zh"},
        client,
    )
    assert [item["anchor_id"] for item in card["anchors"]] == ["A1", "A2"]
    assert card["events"][0]["linked_anchor_ids"] == ["A1", "A2"]
    assert card["metadata"]["card_status"] == "machine_validated"
    assert not validate_source_card(card)
    assert [call["task"] for call in client.calls] == ["extract_source_anchors", "extract_source_events"]


def test_invalid_source_card_must_be_fully_repaired():
    valid_card = {
        "sentences": [{"sentence_id": "S1", "sentence_text": "Mark left.", "anchor_ids": ["A1"]}],
        "anchors": [{"anchor_id": "A1", "sentence_id": "S1", "source_span": "Mark", "normalized_value": "Mark", "anchor_type": "PERSON", "role_hint": "participant", "attributes": {}, "importance": 3, "required": True, "confidence": 0.9}],
        "events": [{"event_id": "V1", "sentence_id": "S1", "evidence_spans": ["Mark left"], "canonical_meaning": "Mark left", "predicate": "leave", "arguments": [{"role": "agent", "anchor_id": "A1", "source_span": "Mark"}], "linked_anchor_ids": ["A1"], "attributes": {}, "importance": 3, "required": True, "confidence": 0.9}],
        "relations": [],
        "allowed_omissions": [],
    }
    client = ScriptedLLMClient(
        [
            {"sentences": [{"sentence_id": "S1", "sentence_text": "Mark left.", "anchor_ids": ["A1"]}], "anchors": [{"anchor_id": "A1", "sentence_id": "S1", "source_span": "John", "importance": 3}]},
            {"events": [], "relations": [], "allowed_omissions": []},
            valid_card,
        ]
    )
    card = build_source_card({"sample_id": "s1", "transcript": "Mark left."}, client)
    assert card["anchors"][0]["source_span"] == "Mark"
    assert card["metadata"]["initial_validation_issues"]
    assert len(client.calls) == 3
