from __future__ import annotations

import argparse
import json

from .config import get_provider_config
from .importers import import_wide_files
from .llm_provider import HTTPJSONClient
from .pipeline import run_pipeline


PROVIDERS = ["deepseek", "openai", "gemini", "custom"]


def main() -> None:
    parser = argparse.ArgumentParser(prog="evisi-eval", description="证据驱动的同传最终译文质量评测")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="运行完整 LLM Agent 评测流程")
    run.add_argument("--samples", required=True, help="源文样本 JSONL")
    run.add_argument("--outputs", required=True, help="同传系统输出 JSONL")
    run.add_argument("--output-dir", default="results")
    run.add_argument("--run-name", default="evaluation_run")
    run.add_argument("--provider", default="deepseek", choices=PROVIDERS)
    run.add_argument("--review-provider", choices=PROVIDERS)
    run.add_argument("--resume", action="store_true")

    check = sub.add_parser("check-provider", help="验证模型配置和 JSON 输出")
    check.add_argument("--provider", default="deepseek", choices=PROVIDERS)

    importer = sub.add_parser("import-data", help="将宽表 JSON/JSONL 转换为标准输入")
    importer.add_argument("--input", required=True, nargs="+")
    importer.add_argument("--samples-output", required=True)
    importer.add_argument("--outputs-output", required=True)

    args = parser.parse_args()
    if args.command == "run":
        metrics = run_pipeline(
            samples_path=args.samples,
            outputs_path=args.outputs,
            output_dir=args.output_dir,
            run_name=args.run_name,
            provider_name=args.provider,
            review_provider_name=args.review_provider,
            resume=args.resume,
        )
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    elif args.command == "check-provider":
        client = HTTPJSONClient(get_provider_config(args.provider))
        response = client.generate_json(
            "Return one JSON object with exactly {\"ok\":true}. JSON only.",
            {"task": "connectivity_check"},
            task="check_provider",
        )
        if response.data.get("ok") is not True:
            raise SystemExit("模型已响应，但没有遵守 JSON 检查协议")
        print(f"连接成功：provider={response.provider} model={response.model}")
    elif args.command == "import-data":
        result = import_wide_files(args.input, args.samples_output, args.outputs_output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
