import json

from evisi_eval.dataset import prepare_dataset


def test_prepare_dataset_normalizes_and_splits(tmp_path):
    samples = tmp_path / "samples.jsonl"
    outputs = tmp_path / "outputs.jsonl"
    samples.write_text(json.dumps({"sample_id": "s1", "transcript": "Hello.", "offline_translation": "你好。"}) + "\n", encoding="utf-8")
    outputs.write_text(json.dumps({"sample_id": "s1", "system_name": "A", "si_translation": "你好。", "system_asr": "Hello."}) + "\n", encoding="utf-8")
    result = prepare_dataset(str(samples), str(outputs), str(tmp_path / "prepared"))
    assert result["samples"] == 1
    source = json.loads((tmp_path / "prepared/source_00_input.jsonl").read_text(encoding="utf-8"))
    target = json.loads((tmp_path / "prepared/target_00_input.jsonl").read_text(encoding="utf-8"))
    assert source["source_text"] == "Hello."
    assert source["reference_translation"] == "你好。"
    assert "system_asr" not in target
    assert (tmp_path / "prepared/samples/s1/source.json").exists()
    assert (tmp_path / "prepared/smoke/target_00_input.jsonl").exists()
