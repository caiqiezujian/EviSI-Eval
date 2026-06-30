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
        f"<tr><td>{_e(name)}</td><td>{_e(row['samples'])}</td>"
        f"<td>{_e(row['average_score'])}</td><td>{_e(row.get('provisional_average_score'))}</td>"
        f"<td>{_e(row.get('final_results', 0))}</td>"
        f"<td>{_e(row.get('provisional_results', 0))}</td>"
        f"<td>{_e(row.get('unscored_results', 0))}</td>"
        + "".join(f"<td>{_e(row['dimension_scores'][key])}</td>" for key in DIMENSION_LABELS)
        + "</tr>"
        for name, row in metrics.get("systems", {}).items()
    )
    dimension_headers = "".join(f"<th>{label}</th>" for label in DIMENSION_LABELS.values())
    sections = "".join(_result_section(result) for result in results)
    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EviSI-Eval v0.5 评测报告</title><style>
body{{font-family:Arial,"Microsoft YaHei",sans-serif;margin:0;background:#f4f5f6;color:#202428}}
main{{max-width:1380px;margin:auto;padding:24px}}header,section{{background:#fff;border:1px solid #d9dee2;border-radius:6px;padding:20px;margin-bottom:16px}}
h1,h2,h3{{margin:0 0 12px}}p{{line-height:1.6}}.score{{font-size:28px;font-weight:700}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
table{{width:100%;border-collapse:collapse;margin:10px 0 18px}}th,td{{border:1px solid #d9dee2;padding:8px;vertical-align:top;text-align:left}}th{{background:#eef1f3}}
.text{{white-space:pre-wrap}}.muted{{color:#5e6870}}@media(max-width:800px){{.grid{{grid-template-columns:1fr}}main{{padding:10px}}}}
</style></head><body><main><header><h1>EviSI-Eval v0.5 同传最终译文评测报告</h1>
<p>结果数：{_e(metrics.get('num_results'))}　失败数：{_e(metrics.get('num_failures'))}　正式结果：{_e(metrics.get('num_final_results'))}　待复核：{_e(metrics.get('num_provisional_results'))}　未评分：{_e(metrics.get('num_unscored_results'))}　正式平均分：{_e(metrics.get('average_score'))}</p>
<table><thead><tr><th>系统</th><th>样本数</th><th>正式均分</th><th>临时均分（不参与排名）</th><th>正式</th><th>待复核</th><th>未评分</th>{dimension_headers}</tr></thead><tbody>{system_rows}</tbody></table>
</header>{sections}</main></body></html>"""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8")


def _result_section(result: dict[str, Any]) -> str:
    diagnostics = result.get("score_diagnostics", {})
    score_rows = "".join(
        f"<tr><td>{_e(DIMENSION_LABELS[key])}</td><td>{_e(result.get('dimension_scores', {}).get(key))}</td>"
        f"<td>{_e(result.get('dimension_weights', {}).get(key))}% / "
        f"{_e(result.get('effective_dimension_weights', {}).get(key))}%</td>"
        f"<td>{_e(_diagnostic_text(diagnostics.get(key, {})))}</td></tr>"
        for key in DIMENSION_LABELS
    )
    eval_rows = "".join(
        f"<tr><td>{_e(row.get('eval_unit_id'))}</td><td>{_e(', '.join(row.get('source_unit_ids', [])))}</td>"
        f"<td class='text'>{_e(row.get('target_unit'))}</td><td>{_e(row.get('alignment_status'))}</td><td>{_e(row.get('reason'))}</td></tr>"
        for row in result.get("eval_units", [])
    )
    judgement_rows = "".join(
        _judgement_rows(result.get(key, []), kind)
        for key, kind in (("anchor_judgements", "Anchor"), ("event_judgements", "Event"), ("relation_judgements", "Relation"))
    ) or "<tr><td colspan='9'>无内容判定</td></tr>"
    evidence_rows = _evidence_rows(result) or "<tr><td colspan='8'>无抽取证据</td></tr>"
    issue_rows = "".join(
        f"<tr><td>{kind}</td><td>{_e(row.get('issue_id'))}</td><td>{_e(row.get('issue_type'))}</td>"
        f"<td>{_e(row.get('target_span'))}</td><td>{_e(row.get('severity'))}</td><td>{_e(row.get('reason'))}</td></tr>"
        for key, kind in (("fluency_issues", "Fluency"), ("si_expression_issues", "SI Expression"))
        for row in result.get(key, [])
    ) or "<tr><td colspan='6'>无表达问题</td></tr>"
    summary = result.get("score_summary", {})
    return f"""<section><h2>{_e(result.get('sample_id'))} · {_e(result.get('system_name'))}</h2>
<p class="score">{_e(result.get('final_score') if result.get('final_score') is not None else '未评分')} <span class="muted">{_e(result.get('score_status'))}</span></p>
<div class="grid"><div><h3>源文</h3><p class="text">{_e(result.get('source_text'))}</p></div><div><h3>同传译文</h3><p class="text">{_e(result.get('si_translation'))}</p></div></div>
<h3>五维得分与诊断</h3><table><thead><tr><th>维度</th><th>分数</th><th>名义/实际权重</th><th>确定性诊断</th></tr></thead><tbody>{score_rows}</tbody></table>
<h3>对齐单元</h3><table><thead><tr><th>ID</th><th>源单元</th><th>译文片段</th><th>状态</th><th>理由</th></tr></thead><tbody>{eval_rows}</tbody></table>
<h3>两侧结构化证据</h3><table><thead><tr><th>侧</th><th>类别</th><th>ID</th><th>类型</th><th>单元</th><th>逐字证据</th><th>规范含义</th><th>重要度</th></tr></thead><tbody>{evidence_rows}</tbody></table>
<h3>内容忠实度判定</h3><table><thead><tr><th>维度</th><th>判定 ID</th><th>源项目</th><th>源证据</th><th>目标证据</th><th>Verdict</th><th>置信度</th><th>处理</th><th>理由</th></tr></thead><tbody>{judgement_rows}</tbody></table>
<h3>表达问题</h3><table><thead><tr><th>维度</th><th>ID</th><th>类型</th><th>译文证据</th><th>严重度</th><th>理由</th></tr></thead><tbody>{issue_rows}</tbody></table>
<h3>总结</h3><p>{_e(summary.get('overall_judgement'))}</p><p class="muted">优势：{_e('；'.join(summary.get('main_strengths', [])))}<br>问题：{_e('；'.join(summary.get('main_errors', [])))}<br>不确定项：{_e('；'.join(summary.get('uncertain_points', [])))}</p></section>"""


def _judgement_rows(rows: list[dict[str, Any]], kind: str) -> str:
    lower = kind.lower()
    return "".join(
        f"<tr><td>{kind}</td><td>{_e(row.get('judgement_id'))}</td>"
        f"<td>{_e(row.get(f'source_{lower}_id'))}</td>"
        f"<td>{_e(' | '.join(row.get('source_evidence_spans', [])))}</td>"
        f"<td>{_e(' | '.join(row.get('target_evidence_spans', [])))}</td>"
        f"<td>{_e(row.get('verdict'))}</td><td>{_e(row.get('confidence'))}</td>"
        f"<td>{_e(row.get('resolution'))}</td><td>{_e(row.get('reason'))}</td></tr>"
        for row in rows
    )


def _evidence_rows(result: dict[str, Any]) -> str:
    configs = (
        ("源", "Anchor", "source_anchors", "source_anchor_id", "anchor_type", "source_unit_id", "evidence_span", "normalized_meaning"),
        ("目标", "Anchor", "target_anchors", "target_anchor_id", "anchor_type", "eval_unit_id", "evidence_span", "normalized_meaning"),
        ("源", "Event", "source_events", "source_event_id", "event_type", "source_unit_id", "evidence_span", "canonical_meaning"),
        ("目标", "Event", "target_events", "target_event_id", "event_type", "eval_unit_id", "evidence_span", "canonical_meaning"),
        ("源", "Relation", "source_relations", "source_relation_id", "relation_type", "source_unit_ids", "evidence_spans", "relation_meaning"),
        ("目标", "Relation", "target_relations", "target_relation_id", "relation_type", "eval_unit_ids", "evidence_spans", "relation_meaning"),
    )
    rows = []
    for side, kind, key, id_key, type_key, unit_key, evidence_key, meaning_key in configs:
        for item in result.get(key, []):
            units = item.get(unit_key, [])
            evidence = item.get(evidence_key, [])
            if not isinstance(units, list):
                units = [units]
            if not isinstance(evidence, list):
                evidence = [evidence]
            rows.append(
                f"<tr><td>{side}</td><td>{kind}</td><td>{_e(item.get(id_key))}</td>"
                f"<td>{_e(item.get(type_key))}</td><td>{_e(', '.join(str(v) for v in units))}</td>"
                f"<td>{_e(' | '.join(str(v) for v in evidence))}</td><td>{_e(item.get(meaning_key))}</td>"
                f"<td>{_e(item.get('importance', ''))}</td></tr>"
            )
    return "".join(rows)


def _diagnostic_text(value: dict[str, Any]) -> str:
    if "coverage" in value:
        return (
            f"status={value.get('decision_status')}; coverage={value.get('coverage')}%; "
            f"verdicts={value.get('verdict_counts', {})}; "
            f"low_confidence={value.get('low_confidence_count', 0)}"
        )
    return f"issues={value.get('issue_count', 0)}; deduction={value.get('total_deduction', 0)}"


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))
