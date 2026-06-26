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

