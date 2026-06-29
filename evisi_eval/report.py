from __future__ import annotations

import html
from pathlib import Path
from typing import Any


DIMENSION_LABELS = {
    "anchor_fidelity": "Anchor 忠实度",
    "event_fidelity": "Event 忠实度",
    "relation_fidelity": "Relation 忠实度",
    "fluency": "流利度",
    "si_expression": "同传表达",
}


def export_html_report(
    results: list[dict[str, Any]], metrics: dict[str, Any], output_path: str | Path
) -> None:
    system_rows = "".join(
        f"<tr><td>{_e(name)}</td><td>{_e(row['samples'])}</td><td>{_e(row['average_score'])}</td>"
        + "".join(f"<td>{_e(row['dimension_scores'][key])}</td>" for key in DIMENSION_LABELS)
        + "</tr>"
        for name, row in metrics.get("systems", {}).items()
    )
    sections = "".join(_result_section(result) for result in results)
    dimension_headers = "".join(f"<th>{label}</th>" for label in DIMENSION_LABELS.values())
    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EviSI-Eval v0.3 评测报告</title><style>
body{{font-family:Arial,"Microsoft YaHei",sans-serif;margin:0;background:#f4f5f6;color:#202428}}
main{{max-width:1320px;margin:auto;padding:24px}}header,section{{background:#fff;border:1px solid #d9dee2;border-radius:6px;padding:20px;margin-bottom:16px}}
h1,h2,h3{{margin:0 0 12px}}p{{line-height:1.6}}.score{{font-size:28px;font-weight:700}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
table{{width:100%;border-collapse:collapse;margin:10px 0 18px}}th,td{{border:1px solid #d9dee2;padding:8px;vertical-align:top;text-align:left}}th{{background:#eef1f3}}
.text{{white-space:pre-wrap}}.muted{{color:#5e6870}}@media(max-width:800px){{.grid{{grid-template-columns:1fr}}main{{padding:10px}}}}
</style></head><body><main><header><h1>EviSI-Eval v0.3 同传最终译文评测报告</h1>
<p>结果数：{_e(metrics.get('num_results'))}　失败数：{_e(metrics.get('num_failures'))}　平均分：{_e(metrics.get('average_score'))}</p>
<table><thead><tr><th>系统</th><th>样本数</th><th>总分</th>{dimension_headers}</tr></thead><tbody>{system_rows}</tbody></table></header>{sections}</main></body></html>"""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8")


def _result_section(result: dict[str, Any]) -> str:
    score_rows = "".join(
        f"<tr><td>{_e(DIMENSION_LABELS[key])}</td><td>{_e(result['dimension_scores'][key])}</td><td>{_e(result['dimension_weights'][key])}%</td><td>{_e(result['dimension_score_explanations'][key])}</td></tr>"
        for key in DIMENSION_LABELS
    )
    eval_rows = "".join(
        f"<tr><td>{_e(row.get('eval_unit_id'))}</td><td>{_e(', '.join(row.get('source_unit_ids', [])))}</td><td class='text'>{_e(row.get('target_unit'))}</td><td>{_e(row.get('alignment_status'))}</td><td>{_e(row.get('reason'))}</td></tr>"
        for row in result.get("eval_units", [])
    )
    judgement_rows = "".join(
        _judgement_rows(result.get(key, []), kind)
        for key, kind in (
            ("anchor_judgements", "Anchor"),
            ("event_judgements", "Event"),
            ("relation_judgements", "Relation"),
        )
    ) or "<tr><td colspan='6'>无内容 judgement</td></tr>"
    issue_rows = "".join(
        f"<tr><td>{kind}</td><td>{_e(row.get('issue_id'))}</td><td>{_e(row.get('target_span'))}</td><td>{_e(row.get('severity'))}</td><td>{_e(row.get('issue_description'))}</td></tr>"
        for key, kind in (("fluency_issues", "Fluency"), ("si_expression_issues", "SI Expression"))
        for row in result.get(key, [])
    ) or "<tr><td colspan='5'>无表达类问题</td></tr>"
    summary = result.get("score_summary", {})
    return f"""<section><h2>{_e(result.get('sample_id'))} · {_e(result.get('system_name'))}</h2>
<p class="score">{_e(result.get('final_score'))}</p>
<div class="grid"><div><h3>源文</h3><p class="text">{_e(result.get('source_text'))}</p></div><div><h3>同传译文</h3><p class="text">{_e(result.get('si_translation'))}</p></div></div>
<h3>五维得分</h3><table><thead><tr><th>维度</th><th>分数</th><th>权重</th><th>证据说明</th></tr></thead><tbody>{score_rows}</tbody></table>
<h3>Eval Units</h3><table><thead><tr><th>ID</th><th>源单元</th><th>译文片段</th><th>状态</th><th>理由</th></tr></thead><tbody>{eval_rows}</tbody></table>
<h3>内容忠实度 Judgements</h3><table><thead><tr><th>维度</th><th>源项目</th><th>源内容</th><th>译文匹配</th><th>判定</th><th>说明</th></tr></thead><tbody>{judgement_rows}</tbody></table>
<h3>表达问题</h3><table><thead><tr><th>维度</th><th>ID</th><th>译文证据</th><th>严重度</th><th>说明</th></tr></thead><tbody>{issue_rows}</tbody></table>
<h3>总结</h3><p>{_e(summary.get('overall_judgement'))}</p><p class="muted">优势：{_e('；'.join(summary.get('main_strengths', [])))}<br>问题：{_e('；'.join(summary.get('main_errors', [])))}<br>不确定：{_e('；'.join(summary.get('uncertain_points', [])))}</p></section>"""


def _judgement_rows(rows: list[dict[str, Any]], kind: str) -> str:
    prefix = kind.lower()
    source_id_key = f"source_{prefix}_id"
    source_text_key = f"source_{prefix}"
    return "".join(
        f"<tr><td>{kind}</td><td>{_e(row.get(source_id_key))}</td><td>{_e(row.get(source_text_key))}</td><td>{_e(row.get('target_match'))}</td><td>{_e(row.get('verdict'))}</td><td>{_e(row.get('explanation'))}</td></tr>"
        for row in rows
    )


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))
