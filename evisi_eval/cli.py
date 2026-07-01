"""EviSI-Eval v0.7 CLI — Source+Reference joint extraction + positional SI matching."""

from __future__ import annotations

import argparse
import json

from .config import get_provider_config
from .dataset import prepare_dataset
from .importers import import_wide_files
from .llm_provider import HTTPJSONClient
from .v07_pipeline import check_v07_input_files, run_v07_pipeline


PROVIDERS = ["deepseek", "openai", "gemini", "custom"]


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="evisi-eval",
        description="EviSI-Eval v0.7 — Source+Reference 联合抽取 + SI 位置匹配 + 确定性计分",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── v0.7 evaluation ─────────────────────────────────────────────
    run_v07 = sub.add_parser(
        "run",
        help="v0.7: Source+Reference 联合抽取 + SI 位置匹配 + 确定性计分",
    )
    run_v07.add_argument("--samples", required=True, help="含参考译文的样本 JSONL")
    run_v07.add_argument("--outputs", required=True, help="同传系统输出 JSONL")
    run_v07.add_argument("--output-dir", default="results")
    run_v07.add_argument("--run-name", default="v07_evaluation")
    run_v07.add_argument("--provider", default="deepseek", choices=PROVIDERS)
    run_v07.add_argument("--resume", action="store_true")
    run_v07.add_argument("--sample-id", action="append", dest="sample_ids")
    run_v07.add_argument("--system-name", action="append", dest="system_names")
    run_v07.add_argument("--limit-samples", type=int)
    run_v07.add_argument("--limit-outputs", type=int)

    # ── input validation ────────────────────────────────────────────
    check_input = sub.add_parser(
        "check-input", help="校验并汇总 v0.7 输入，不调用大模型"
    )
    check_input.add_argument("--samples", required=True, help="样本 JSONL")
    check_input.add_argument("--outputs", required=True, help="同传系统输出 JSONL")

    # ── utilities ───────────────────────────────────────────────────
    prepare = sub.add_parser("prepare-data", help="校验并按样本拆分标准输入")
    prepare.add_argument("--samples", required=True)
    prepare.add_argument("--outputs", required=True)
    prepare.add_argument("--output-dir", required=True)

    check = sub.add_parser("check-provider", help="验证模型配置和 JSON 输出能力")
    check.add_argument("--provider", default="deepseek", choices=PROVIDERS)

    importer = sub.add_parser("import-data", help="把宽表 JSON/JSONL 转换为标准输入")
    importer.add_argument("--input", required=True, nargs="+")
    importer.add_argument("--samples-output", required=True)
    importer.add_argument("--outputs-output", required=True)

    # ── dispatch ────────────────────────────────────────────────────
    args = parser.parse_args()

    if args.command == "run":
        result = run_v07_pipeline(
            samples_path=args.samples,
            outputs_path=args.outputs,
            output_dir=args.output_dir,
            run_name=args.run_name,
            provider_name=args.provider,
            resume=args.resume,
            sample_ids=args.sample_ids,
            system_names=args.system_names,
            limit_samples=args.limit_samples,
            limit_outputs=args.limit_outputs,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("num_failures"):
            raise SystemExit(1)

    elif args.command == "check-input":
        result = check_v07_input_files(args.samples, args.outputs)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "prepare-data":
        result = prepare_dataset(args.samples, args.outputs, args.output_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "check-provider":
        client = HTTPJSONClient(get_provider_config(args.provider))
        response = client.generate_json(
            'Return one JSON object with exactly {"ok":true}. JSON only.',
            {"task": "connectivity_check"},
            task="check_provider",
        )
        if response.data.get("ok") is not True:
            raise SystemExit("模型已响应，但没有遵守 JSON 检查协议")
        print(f"连接成功：provider={response.provider} model={response.model}")

    elif args.command == "import-data":
        result = import_wide_files(args.input, args.samples_output, args.outputs_output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
