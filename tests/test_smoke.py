from evisi_eval.aggregator import evaluate_translation
from evisi_eval.card_builder import build_card


def test_fact_cap_for_wrong_percentage():
    card = build_card(
        {
            "sample_id": "s1",
            "source_text": "Apple reported a 15% increase in revenue in Q2.",
            "offline_translation": "苹果第二季度收入增长15%。"
        }
    )
    result = evaluate_translation(card, "sys", "谷歌第二季度收入增长了50%。")
    assert result["final_score"] <= 70
    assert result["attributed_errors"]


def test_reference_assisted_proposition_mode():
    card = build_card(
        {
            "sample_id": "s2",
            "transcript": "I go to work.",
            "offline_translation": "我去上班。"
        }
    )
    good = evaluate_translation(card, "sys", "我去上班。")
    bad = evaluate_translation(card, "sys", "我去打球。")
    assert good["evaluation_mode"] == "reference_assisted"
    assert good["final_score"] == 100
    assert bad["final_score"] < 100
    assert any(e["dimension"] == "core_proposition_coverage" for e in bad["attributed_errors"])


def test_source_only_same_script_proposition_mode():
    card = build_card(
        {
            "sample_id": "s3",
            "transcript": "我去上班。"
        }
    )
    good = evaluate_translation(card, "sys", "我去上班。")
    bad = evaluate_translation(card, "sys", "我去打球。")
    assert good["evaluation_mode"] == "source_only"
    assert good["final_score"] == 100
    assert bad["final_score"] < 100
