from __future__ import annotations

import argparse
import json

from .config import get_provider_config
from .dataset import prepare_dataset
from .importers import import_wide_files
from .llm_provider import HTTPJSONClient
from .pipeline import run_pipeline
from .v06_pipeline import check_v06_input_files, run_v06_pipeline


PROVIDERS = ["deepseek", "openai", "gemini", "custom"]


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="evisi-eval",
        description="EviSI-Eval v0.6 源文条件化同传最终译文评测",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="运行冻结源证据、多 Agent 复核与确定性计分流程")
    run.add_argument("--samples", required=True, help="样本 JSONL")
    run.add_argument("--outputs", required=True, help="系统输出 JSONL")
    run.add_argument("--output-dir", default="results")
    run.add_argument("--run-name", default="evaluation_run")
    run.add_argument("--provider", default="deepseek", choices=PROVIDERS)
    run.add_argument(
        "--review-provider",
        choices=PROVIDERS,
        help="独立复核/裁决模型提供方；默认读取 EVISI_REVIEW_PROVIDER，否则与主模型相同",
    )
    run.add_argument("--resume", action="store_true")
    run.add_argument("--sample-id", action="append", dest="sample_ids")
    run.add_argument("--system-name", action="append", dest="system_names")
    run.add_argument("--limit-samples", type=int)
    run.add_argument("--limit-outputs", type=int)

    run_v06 = sub.add_parser(
        "run-v06",
        help="运行 Source 基准、Reference/SI 投影式抽取和确定性计分流程",
    )
    run_v06.add_argument("--samples", required=True, help="含参考译文的样本 JSONL")
    run_v06.add_argument("--outputs", required=True, help="同传系统输出 JSONL")
    run_v06.add_argument("--output-dir", default="results")
    run_v06.add_argument("--run-name", default="v06_evaluation")
    run_v06.add_argument("--provider", default="deepseek", choices=PROVIDERS)
    run_v06.add_argument("--resume", action="store_true")
    run_v06.add_argument("--sample-id", action="append", dest="sample_ids")
    run_v06.add_argument("--system-name", action="append", dest="system_names")
    run_v06.add_argument("--limit-samples", type=int)
    run_v06.add_argument("--limit-outputs", type=int)

    check_v06_input = sub.add_parser(
        "check-v06-input", help="仅校验并汇总 v0.6 输入，不调用大模型"
    )
    check_v06_input.add_argument("--samples", required=True, help="样本 JSONL")
    check_v06_input.add_argument("--outputs", required=True, help="同传系统输出 JSONL")

    prepare = sub.add_parser("prepare-data", help="校验并按样本拆分 v0.5 标准输入")
    prepare.add_argument("--samples", required=True)
    prepare.add_argument("--outputs", required=True)
    prepare.add_argument("--output-dir", required=True)

    check = sub.add_parser("check-provider", help="验证模型配置和 JSON 输出能力")
    check.add_argument("--provider", default="deepseek", choices=PROVIDERS)

    importer = sub.add_parser("import-data", help="把宽表 JSON/JSONL 转换为标准输入")
    importer.add_argument("--input", required=True, nargs="+")
    importer.add_argument("--samples-output", required=True)
    importer.add_argument("--outputs-output", required=True)

    args = parser.parse_args()
    if args.command == "run":
        result = run_pipeline(
            samples_path=args.samples,
            outputs_path=args.outputs,
            output_dir=args.output_dir,
            run_name=args.run_name,
            provider_name=args.provider,
            review_provider_name=args.review_provider,
            resume=args.resume,
            sample_ids=args.sample_ids,
            system_names=args.system_names,
            limit_samples=args.limit_samples,
            limit_outputs=args.limit_outputs,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "run-v06":
        result = run_v06_pipeline(
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
    elif args.command == "check-v06-input":
        result = check_v06_input_files(args.samples, args.outputs)
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
