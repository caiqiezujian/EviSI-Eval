from __future__ import annotations

import csv
import html
from pathlib import Path


def export_html(results: list[dict], output: str | Path) -> None:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for result in results:
        errors = result.get("attributed_errors", [])
        error_html = "<br>".join(
            html.escape(f"{e['severity']} {e['error_type']}: {e['source_span']} -> {e.get('target_span')} (-{e['deduction']})")
            for e in errors
        )
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(result.get('sample_id')))}</td>"
            f"<td>{html.escape(str(result.get('system_name')))}</td>"
            f"<td>{html.escape(str(result.get('expected_label', '')))}</td>"
            f"<td>{html.escape(str(result.get('final_score')))}</td>"
            f"<td>{html.escape(str(result.get('cap_reason')))}</td>"
            f"<td>{error_html}</td>"
            "</tr>"
        )
    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>EviSI-Eval Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2933; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #d8dee4; padding: 8px; vertical-align: top; }}
    th {{ background: #f3f4f6; text-align: left; }}
    td:nth-child(3) {{ font-weight: 700; }}
  </style>
</head>
<body>
  <h1>EviSI-Eval v0.1 Report</h1>
  <p>Scope: fact accuracy and score caps only.</p>
  <table>
    <thead><tr><th>Sample</th><th>System</th><th>Expected Label</th><th>Score</th><th>Cap</th><th>Errors</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</body>
</html>
"""
    target.write_text(page, encoding="utf-8")


def export_csv(results: list[dict], output: str | Path) -> None:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["sample_id", "system_name", "expected_label", "final_score", "cap_triggered", "cap_reason", "error_count"],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "sample_id": result.get("sample_id"),
                    "system_name": result.get("system_name"),
                    "expected_label": result.get("expected_label"),
                    "final_score": result.get("final_score"),
                    "cap_triggered": result.get("cap_triggered"),
                    "cap_reason": result.get("cap_reason"),
                    "error_count": len(result.get("attributed_errors", [])),
                }
            )
