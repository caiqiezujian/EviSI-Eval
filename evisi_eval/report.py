from __future__ import annotations

import html
from pathlib import Path
from typing import Any


DIMENSION_NAMES = {
    "anchor_accuracy": "事实锚点准确性",
    "event_preservation": "事件语义保持",
    "relation_preservation": "逻辑关系保持",
    "target_fluency": "流利度与可理解性",
    "expression_efficiency": "表达效率与简洁性",
}


def export_html_report(
    results: list[dict[str, Any]], metrics: dict[str, Any], output_path: str | Path
) -> None:
    sections = []
    for result in results:
        sentence_rows = "".join(
            f"<tr><td>{_e(item.get('source_sentence_id'))}</td><td>{_e(item.get('source_sentence_text'))}</td><td>{_e(' | '.join(item.get('target_spans', [])))}</td><td>{_e(item.get('alignment_type'))}</td><td>{_e(item.get('confidence'))}</td></tr>"
            for item in result.get("sentence_alignment", {}).get("sentence_alignments", [])
        ) or '<tr><td colspan="5">无句级对齐结果</td></tr>'
        dimension_rows = "".join(
            f"<tr><td>{_e(DIMENSION_NAMES.get(key, key))}</td><td>{_e(value.get('score'))}</td><td>{_e(value.get('max_points'))}</td><td>{_e(value.get('error_count'))}</td></tr>"
            for key, value in result.get("dimension_scores", {}).items()
        )
        error_rows = "".join(
            f"<tr><td>{_e(DIMENSION_NAMES.get(item.get('dimension'), item.get('dimension')))}</td><td>{_e(item.get('item_id'))}</td><td>{_e(item.get('verdict'))}</td><td>{_e(item.get('source_evidence'))}</td><td>{_e(item.get('target_evidence'))}</td><td>{_e(item.get('deduction'))}</td></tr>"
            for item in result.get("attributed_errors", [])
        ) or '<tr><td colspan="6">无已确认错误</td></tr>'
        sections.append(
            f"""
            <section>
              <h2>{_e(result.get('sample_id'))} · {_e(result.get('system_name'))}</h2>
              <p class="score">总分 {_e(result.get('final_score'))}</p>
              <div class="texts"><div><h3>原文</h3><p>{_e(result.get('source_text'))}</p></div><div><h3>同传译文</h3><p>{_e(result.get('si_translation'))}</p></div></div>
              <h3>源句—译文单元对齐</h3><table><thead><tr><th>源句</th><th>源文</th><th>译文单元</th><th>类型</th><th>置信度</th></tr></thead><tbody>{sentence_rows}</tbody></table>
              <h3>维度得分</h3><table><thead><tr><th>维度</th><th>得分</th><th>满分</th><th>错误数</th></tr></thead><tbody>{dimension_rows}</tbody></table>
              <h3>证据化错误</h3><table><thead><tr><th>维度</th><th>项目</th><th>判定</th><th>源文证据</th><th>译文证据</th><th>扣分</th></tr></thead><tbody>{error_rows}</tbody></table>
            </section>
            """
        )
    systems = "".join(
        f"<tr><td>{_e(name)}</td><td>{_e(value.get('samples'))}</td><td>{_e(value.get('average_score'))}</td><td>{_e(value.get('confirmed_errors'))}</td><td>{_e(value.get('pending_reviews'))}</td></tr>"
        for name, value in metrics.get("systems", {}).items()
    )
    document = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EviSI-Eval 评测报告</title><style>
    body{{font-family:Arial,"Microsoft YaHei",sans-serif;margin:0;background:#f5f6f7;color:#202428}}main{{max-width:1280px;margin:auto;padding:28px}}header,section{{background:#fff;border:1px solid #dfe3e6;border-radius:6px;padding:22px;margin-bottom:18px}}h1,h2,h3{{margin-top:0}}table{{width:100%;border-collapse:collapse;margin-bottom:18px}}th,td{{border:1px solid #dfe3e6;padding:8px;text-align:left;vertical-align:top}}th{{background:#f0f2f3}}.texts{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}.texts p{{white-space:pre-wrap;line-height:1.6}}.score{{font-size:24px;font-weight:700}}@media(max-width:800px){{.texts{{grid-template-columns:1fr}}main{{padding:12px}}}}
    </style></head><body><main><header><h1>EviSI-Eval 同传最终译文评测报告</h1><p>结果数：{_e(metrics.get('num_results'))}　失败数：{_e(metrics.get('num_failures'))}　总体均分：{_e(metrics.get('average_score'))}</p><table><thead><tr><th>系统</th><th>样本数</th><th>平均分</th><th>已确认错误</th><th>待复核</th></tr></thead><tbody>{systems}</tbody></table></header>{''.join(sections)}</main></body></html>"""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8")


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))
