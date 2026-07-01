from evisi_eval.importers import convert_wide_rows, read_json_object_stream


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
    assert samples[0]["reference_translation"] == "我去上班。"
    assert samples[0]["source_text"] == "I go to work."
    assert samples[0]["domain"] == "tech"
    assert len(outputs) == 2
    assert outputs[0]["system_name"] == "A"
    assert "system_asr" not in outputs[0]


def test_read_concatenated_json_objects(tmp_path):
    path = tmp_path / "wide.txt"
    path.write_text('{"vid":"a","transcript":"x"}{"vid":"b","transcript":"y"}', encoding="utf-8")
    rows = read_json_object_stream(path)
    assert [row["vid"] for row in rows] == ["a", "b"]
