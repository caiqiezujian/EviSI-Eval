from __future__ import annotations

import html
from collections import defaultdict
from pathlib import Path
from typing import Any


DIMENSION_LABELS = {
    "fact_accuracy": "关键事实保真度",
    "core_proposition_coverage": "核心命题覆盖度",
    "logic_relation_preservation": "逻辑关系保持度",
    "target_language_comprehensibility": "目标语可理解性",
}


def export_agent_html(results: list[dict[str, Any]], output: str | Path) -> None:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    summary = _system_summary(results)
    summary_rows = "".join(
        "<tr>"
        f"<td>{_e(system)}</td><td>{data['count']}</td><td>{data['average']:.2f}</td>"
        + "".join(f"<td>{_score_cell(data['dimensions'].get(key))}</td>" for key in DIMENSION_LABELS)
        + f"<td>{data['errors']}</td><td>{data['reviews']}</td></tr>"
        for system, data in sorted(summary.items(), key=lambda item: (-item[1]["average"], item[0]))
    )
    detail_blocks = "".join(_result_block(result) for result in results)
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EviSI-Eval LLM Agent 评测报告</title>
  <style>
    body {{ margin: 0; color: #17202a; font: 14px/1.55 Arial, "Microsoft YaHei", sans-serif; background: #f5f7f8; }}
    header {{ background: #17324d; color: white; padding: 22px max(24px, calc((100% - 1500px)/2)); }}
    main {{ max-width: 1500px; margin: 0 auto; padding: 20px 24px 48px; }}
    h1 {{ margin: 0 0 4px; font-size: 24px; }} h2 {{ margin-top: 26px; font-size: 19px; }}
    .notice {{ background: #fff4d6; border-left: 4px solid #c48600; padding: 10px 12px; margin: 14px 0; }}
    table {{ width: 100%; border-collapse: collapse; background: white; margin: 8px 0 16px; table-layout: fixed; }}
    th, td {{ border: 1px solid #d7dde2; padding: 7px; vertical-align: top; overflow-wrap: anywhere; }}
    th {{ background: #eaf0f4; text-align: left; }}
    details {{ background: white; border: 1px solid #ccd5dc; margin: 12px 0; }}
    summary {{ cursor: pointer; padding: 12px; font-weight: 700; background: #edf2f5; }}
    .content {{ padding: 4px 14px 16px; }}
    .texts {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }}
    .text-box {{ border: 1px solid #d7dde2; padding: 9px; white-space: pre-wrap; min-height: 70px; }}
    .label {{ font-weight: 700; color: #36536b; margin-bottom: 4px; }}
    .ok {{ color: #176b3a; }} .bad {{ color: #a12828; }} .review {{ color: #915d00; }}
    .dim-grid {{ display: grid; grid-template-columns: repeat(4, minmax(140px, 1fr)); gap: 8px; margin: 12px 0; }}
    .dim {{ border: 1px solid #ccd5dc; padding: 8px; }}
    code {{ font-size: 12px; }}
    @media (max-width: 900px) {{ .texts, .dim-grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
<header><h1>EviSI-Eval LLM Agent 评测报告</h1><div>逐项证据判定 + 确定性聚合；系统名称不进入核验 Prompt</div></header>
<main>
  <div class="notice">报告中的每一项扣分都必须能追溯到 Evaluation Card、原文跨度、译文证据和复核状态。待复核项不应被解释为已确认错误。</div>
  <h2>系统汇总</h2>
  <table><thead><tr><th>系统</th><th>样本数</th><th>平均总分</th>{''.join(f'<th>{label}</th>' for label in DIMENSION_LABELS.values())}<th>确认错误</th><th>待复核</th></tr></thead><tbody>{summary_rows}</tbody></table>
  <h2>逐样本审计</h2>
  {detail_blocks}
</main></body></html>"""
    target.write_text(page, encoding="utf-8")


def _result_block(result: dict[str, Any]) -> str:
    dims = result.get("dimension_scores", {})
    dimension_cards = "".join(
        f"<div class='dim'><div class='label'>{_e(label)}</div>{_dimension_score(dims.get(key, {}))}</div>"
        for key, label in DIMENSION_LABELS.items()
    )
    tables = [
        _item_table("关键事实", result.get("fact_verdicts", []), "fact_id"),
        _item_table("核心命题", result.get("proposition_verdicts", []), "prop_id"),
        _item_table("逻辑关系", result.get("relation_verdicts", []), "relation_id"),
        _item_table("目标语问题", result.get("target_quality_issues", []), "issue_id"),
    ]
    cap = ", ".join(str(x.get("reason")) for x in result.get("cap_reasons", [])) or "无"
    return f"""<details>
<summary>{_e(result.get('sample_id'))} · {_e(result.get('system_name'))} · 总分 {result.get('final_score')} · 封顶 {result.get('score_cap') or '无'}</summary>
<div class="content">
  <div class="texts">
    <div><div class="label">原文 transcript</div><div class="text-box">{_e(result.get('transcript'))}</div></div>
    <div><div class="label">离线参考译文</div><div class="text-box">{_e(result.get('offline_translation') or '未提供')}</div></div>
    <div><div class="label">同传最终译文</div><div class="text-box">{_e(result.get('si_translation'))}</div></div>
  </div>
  <div class="dim-grid">{dimension_cards}</div>
  <p><b>评估有效权重：</b>{result.get('evaluated_weight')} / 100　<b>封顶原因：</b>{_e(cap)}　<b>Evaluation Card：</b><code>{_e(result.get('card_hash'))}</code></p>
  {''.join(tables)}
</div></details>"""


def _item_table(title: str, items: list[dict[str, Any]], id_key: str) -> str:
    if not items:
        return f"<h3>{_e(title)}</h3><p>本样本无适用条目。</p>"
    rows = []
    for item in items:
        verdict = item.get("verdict") or item.get("error_type") or "-"
        css = "bad" if item.get("deduction_accepted") else ("review" if item.get("review_required") else "ok")
        source = item.get("source_span") or item.get("source_cues") or "-"
        review = item.get("review") or {}
        review_text = review.get("decision") or ("待复核" if item.get("review_required") else "不需要")
        rows.append(
            "<tr>"
            f"<td>{_e(item.get(id_key))}</td><td>{_e(source)}</td><td>{_e(item.get('target_span') or '-')}</td>"
            f"<td class='{css}'>{_e(verdict)}</td><td>{item.get('importance', '-')}</td>"
            f"<td>{item.get('confidence', '-')}</td><td>{item.get('item_budget', '-')}</td>"
            f"<td>{item.get('deduction', 0)}</td><td>{_e(review_text)}</td><td>{_e(item.get('reason'))}</td></tr>"
        )
    return f"""<h3>{_e(title)}</h3><table><thead><tr><th>ID</th><th>原文关键点</th><th>译文证据</th><th>判定</th><th>重要度</th><th>置信度</th><th>条目预算</th><th>扣分</th><th>复核</th><th>理由</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"""


def _system_summary(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[str(result.get("system_name", "system"))].append(result)
    output = {}
    for system, rows in grouped.items():
        dimensions = {}
        for key in DIMENSION_LABELS:
            values = [r.get("dimension_scores", {}).get(key, {}).get("score") for r in rows]
            numeric = [float(v) for v in values if isinstance(v, (int, float))]
            dimensions[key] = sum(numeric) / len(numeric) if numeric else None
        output[system] = {
            "count": len(rows),
            "average": sum(float(r.get("final_score", 0)) for r in rows) / len(rows),
            "dimensions": dimensions,
            "errors": sum(len(r.get("attributed_errors", [])) for r in rows),
            "reviews": sum(len(r.get("review_queue", [])) for r in rows),
        }
    return output


def _dimension_score(value: dict[str, Any]) -> str:
    if not value or not value.get("applicable"):
        return "不适用"
    return f"<b>{value.get('score')}</b> / {value.get('max_points')}<br>扣分 {value.get('deduction')}"


def _score_cell(value: float | None) -> str:
    return "不适用" if value is None else f"{value:.2f}"


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))
