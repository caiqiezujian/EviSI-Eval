from evisi_eval.validation import (
    validate_eval_units,
    validate_source_units,
    weighted_score,
)


def test_lossless_source_and_target_segmentation_contracts():
    source = "One. Two."
    source_artifact = {
        "source_units": [
            {"source_unit_id": "S1", "source_unit": "One. "},
            {"source_unit_id": "S2", "source_unit": "Two."},
        ]
    }
    assert not validate_source_units(source_artifact, source)

    target = "一。二。"
    eval_artifact = {
        "eval_units": [
            {"eval_unit_id": "E1", "source_unit_ids": ["S1"], "target_unit": "一。", "alignment_status": "aligned", "reason": "aligned"},
            {"eval_unit_id": "E2", "source_unit_ids": ["S2"], "target_unit": "二。", "alignment_status": "aligned", "reason": "aligned"},
        ]
    }
    assert not validate_eval_units(eval_artifact, source_artifact["source_units"], target)
    eval_artifact["eval_units"][1]["target_unit"] = "二"
    assert any("concatenate exactly" in issue for issue in validate_eval_units(eval_artifact, source_artifact["source_units"], target))


def test_fixed_weight_formula():
    assert weighted_score({
        "anchor_fidelity": 90,
        "event_fidelity": 80,
        "relation_fidelity": 70,
        "fluency": 60,
        "si_expression": 50,
    }) == 75.0
