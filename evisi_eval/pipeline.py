from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .aggregator import evaluate_translation
from .card_builder import build_card
from .io_utils import read_jsonl, write_jsonl
from .models import EvaluationCard
from .report import export_html


def run_pipeline(
    samples_path: str,
    outputs_path: str,
    output_dir: str = "results",
    run_name: str = "demo",
    skip_card_build: bool = False,
) -> dict:
    run_root = Path(output_dir) / run_name
    card_path = run_root / "cards" / "cards.jsonl"
    eval_dir = run_root / "evaluation_result" / "evisi_eval"
    result_path = eval_dir / "results.jsonl"
    metrics_path = eval_dir / "metrics.json"
    bad_cases_path = eval_dir / "bad_cases.jsonl"
    not_pass_path = eval_dir / "not_pass.jsonl"
    report_path = eval_dir / "report.html"

    run_root.mkdir(parents=True, exist_ok=True)
    eval_dir.mkdir(parents=True, exist_ok=True)

    if skip_card_build and card_path.exists():
        cards = {row["sample_id"]: EvaluationCard.from_dict(row) for row in read_jsonl(card_path)}
    else:
        sample_rows = read_jsonl(samples_path)
        card_rows = [build_card(row).to_dict() for row in sample_rows]
        write_jsonl(card_path, card_rows)
        cards = {row["sample_id"]: EvaluationCard.from_dict(row) for row in card_rows}

    results = []
    for row in read_jsonl(outputs_path):
        sample_id = row["sample_id"]
        if sample_id not in cards:
            raise KeyError(f"No card found for sample_id={sample_id}")
        result = evaluate_translation(cards[sample_id], row.get("system_name", "system"), row["si_translation"])
        for optional in ("expected_label", "expected_errors", "label_notes"):
            if optional in row:
                result[optional] = row[optional]
        results.append(result)

    write_jsonl(result_path, results)
    bad_cases = [r for r in results if r.get("attributed_errors")]
    not_pass = [r for r in results if float(r.get("final_score", 0)) < 80]
    write_jsonl(bad_cases_path, bad_cases)
    write_jsonl(not_pass_path, not_pass)
    export_html(results, report_path)

    metrics = compute_metrics(results)
    metrics["paths"] = {
        "cards": str(card_path),
        "results": str(result_path),
        "metrics": str(metrics_path),
        "bad_cases": str(bad_cases_path),
        "not_pass": str(not_pass_path),
        "report": str(report_path),
    }
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return metrics


def compute_metrics(results: list[dict]) -> dict:
    scores = [float(r.get("final_score", 0)) for r in results]
    by_mode: dict[str, list[float]] = defaultdict(list)
    by_label: dict[str, list[float]] = defaultdict(list)
    for row in results:
        by_mode[row.get("evaluation_mode", "unknown")].append(float(row.get("final_score", 0)))
        if row.get("expected_label"):
            by_label[row["expected_label"]].append(float(row.get("final_score", 0)))
    return {
        "version": "0.2.0",
        "num_results": len(results),
        "average_score": _mean(scores),
        "cap_rate": _mean([1.0 if r.get("cap_triggered") else 0.0 for r in results]),
        "review_required_count": sum(int(r.get("metadata", {}).get("review_required_count", 0)) for r in results),
        "error_count": sum(len(r.get("attributed_errors", [])) for r in results),
        "by_mode": {k: {"count": len(v), "average_score": _mean(v)} for k, v in sorted(by_mode.items())},
        "by_expected_label": {k: {"count": len(v), "average_score": _mean(v)} for k, v in sorted(by_label.items())},
    }


def print_summary(metrics: dict) -> None:
    print("\n" + "=" * 64)
    print(f"{'Metric':<32} {'Value':>20}")
    print("-" * 64)
    for key in ("num_results", "average_score", "cap_rate", "review_required_count", "error_count"):
        print(f"{key:<32} {metrics.get(key)!s:>20}")
    print("-" * 64)
    for mode, data in metrics.get("by_mode", {}).items():
        print(f"mode:{mode:<27} {data['average_score']:>20.2f}")
    print("=" * 64)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)

