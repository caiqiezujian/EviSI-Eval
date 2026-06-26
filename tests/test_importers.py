from evisi_eval.importers import convert_wide_rows, read_json_object_stream
from evisi_eval.card_builder import build_card


def test_convert_wide_rows():
    rows = [
        {
            "vid": "en2zh-01-tech_001",
            "transcript": "I go to work.",
            "translation": "我去上班。",
            "A_asr": "I go to work.",
            "A_trans": "我去上班。",
            "B_trans": "我去打球。",
        }
    ]
    samples, outputs = convert_wide_rows(rows)
    assert samples[0]["sample_id"] == "en2zh-01-tech_001"
    assert samples[0]["offline_translation"] == "我去上班。"
    assert samples[0]["domain"] == "tech"
    assert len(outputs) == 2
    assert outputs[0]["system_name"] == "A"
    assert outputs[0]["system_asr"] == "I go to work."


def test_read_concatenated_json_objects(tmp_path):
    path = tmp_path / "wide.txt"
    path.write_text('{"vid":"a","transcript":"x"}{"vid":"b","transcript":"y"}', encoding="utf-8")
    rows = read_json_object_stream(path)
    assert [row["vid"] for row in rows] == ["a", "b"]


def test_unaligned_long_reference_uses_document_level_proposition():
    card = build_card(
        {
            "sample_id": "long",
            "transcript": "Okay, cool. Mark explained the cache design. It reduces latency. Users see faster pages.",
            "offline_translation": "马克解释了缓存设计，可以降低延迟，让用户更快看到页面。",
        }
    )
    assert len(card.propositions) == 1
    assert card.propositions[0]["importance"] == 1
    assert "Okay, cool." in card.propositions[0]["source_span"]
