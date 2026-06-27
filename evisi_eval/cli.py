from __future__ import annotations

import argparse
from pathlib import Path

from .aggregator import evaluate_translation
from .agent_pipeline import run_agent_pipeline
from .api_check import check_openai_api, check_provider_api
from .card_builder import build_card
from .io_utils import read_jsonl, write_jsonl
from .importers import import_wide_files
from .models import EvaluationCard
from .report import export_csv, export_html


def main() -> None:
    parser = argparse.ArgumentParser(prog="evisi-eval")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-card", help="Build Evaluation Cards from raw samples")
    build.add_argument("--input", required=True)
    build.add_argument("--output", required=True)

    run = sub.add_parser("run-eval", help="Evaluate SI outputs against cards")
    run.add_argument("--cards", required=True)
    run.add_argument("--outputs", required=True)
    run.add_argument("--output", required=True)

    report = sub.add_parser("export-report", help="Export HTML or CSV report")
    report.add_argument("--input", required=True)
    report.add_argument("--output", required=True)

    api = sub.add_parser("check-api", help="Safely check OpenAI API connectivity")
    api.add_argument("--model", default="gpt-4.1-mini")

    provider_check = sub.add_parser("check-provider", help="Check a configured LLM provider")
    provider_check.add_argument("--provider", default="deepseek", choices=["deepseek", "openai", "gemini", "custom"])

    agent = sub.add_parser("run-agent", help="Run the evidence-driven LLM evaluation agent")
    agent.add_argument("--samples", required=True)
    agent.add_argument("--outputs", required=True)
    agent.add_argument("--output-dir", default="results")
    agent.add_argument("--run-name", default="agent_run")
    agent.add_argument("--provider", default="deepseek", choices=["deepseek", "openai", "gemini", "custom"])
    agent.add_argument("--review-provider", choices=["deepseek", "openai", "gemini", "custom"])
    agent.add_argument("--skip-card-build", action="store_true")
    agent.add_argument("--resume", action="store_true", help="Resume from cards and partial_results.jsonl")

    importer = sub.add_parser("import-wide", help="Import wide JSON/JSONL files into EviSI samples and outputs")
    importer.add_argument("--input", required=True, nargs="+")
    importer.add_argument("--samples-output", required=True)
    importer.add_argument("--outputs-output", required=True)

    args = parser.parse_args()
    if args.command == "build-card":
        cmd_build_card(args.input, args.output)
    elif args.command == "run-eval":
        cmd_run_eval(args.cards, args.outputs, args.output)
    elif args.command == "export-report":
        cmd_export_report(args.input, args.output)
    elif args.command == "check-api":
        cmd_check_api(args.model)
    elif args.command == "check-provider":
        cmd_check_provider(args.provider)
    elif args.command == "run-agent":
        cmd_run_agent(
            args.samples,
            args.outputs,
            args.output_dir,
            args.run_name,
            args.provider,
            args.review_provider,
            args.skip_card_build,
            args.resume,
        )
    elif args.command == "import-wide":
        cmd_import_wide(args.input, args.samples_output, args.outputs_output)


def cmd_build_card(input_path: str, output_path: str) -> None:
    rows = read_jsonl(input_path)
    cards = [build_card(row).to_dict() for row in rows]
    write_jsonl(output_path, cards)
    print(f"Wrote {len(cards)} cards to {output_path}")


def cmd_run_eval(cards_path: str, outputs_path: str, output_path: str) -> None:
    cards = {row["sample_id"]: EvaluationCard.from_dict(row) for row in read_jsonl(cards_path)}
    outputs = read_jsonl(outputs_path)
    results = []
    for row in outputs:
        sample_id = row["sample_id"]
        if sample_id not in cards:
            raise KeyError(f"No card found for sample_id={sample_id}")
        result = evaluate_translation(cards[sample_id], row.get("system_name", "system"), row["si_translation"])
        if "expected_label" in row:
            result["expected_label"] = row["expected_label"]
        if "expected_errors" in row:
            result["expected_errors"] = row["expected_errors"]
        if "label_notes" in row:
            result["label_notes"] = row["label_notes"]
        results.append(result)
    write_jsonl(output_path, results)
    print(f"Wrote {len(results)} results to {output_path}")


def cmd_export_report(input_path: str, output_path: str) -> None:
    results = read_jsonl(input_path)
    suffix = Path(output_path).suffix.lower()
    if suffix == ".csv":
        export_csv(results, output_path)
    else:
        export_html(results, output_path)
    print(f"Wrote report to {output_path}")


def cmd_check_api(model: str) -> None:
    result = check_openai_api(model=model)
    if result["ok"]:
        print(f"OpenAI API check passed with model={result.get('model')}; response={result.get('response_preview')}")
    else:
        print(f"OpenAI API check failed: {result.get('reason')}")
        raise SystemExit(1)


def cmd_check_provider(provider: str) -> None:
    result = check_provider_api(provider)
    if result["ok"]:
        print(f"Provider check passed: provider={result['provider']} model={result['model']}")
        return
    print(f"Provider check failed: {result.get('reason', 'provider did not return the required JSON')}")
    raise SystemExit(1)


def cmd_run_agent(
    samples_path: str,
    outputs_path: str,
    output_dir: str,
    run_name: str,
    provider: str,
    review_provider: str | None,
    skip_card_build: bool,
    resume: bool,
) -> None:
    metrics = run_agent_pipeline(
        samples_path=samples_path,
        outputs_path=outputs_path,
        output_dir=output_dir,
        run_name=run_name,
        provider_name=provider,
        review_provider_name=review_provider,
        skip_card_build=skip_card_build,
        resume=resume,
    )
    print(f"Agent run complete: {metrics['num_results']} results; average={metrics['average_score']}")
    print(f"Report: {metrics['paths']['report']}")


def cmd_import_wide(input_paths: list[str], samples_output: str, outputs_output: str) -> None:
    result = import_wide_files(input_paths, samples_output, outputs_output)
    print(
        "Imported "
        f"{result['samples']} samples and {result['outputs']} system outputs "
        f"from {len(result['input_files'])} file(s)."
    )
    print(f"Systems: {', '.join(result['systems'])}")
    print(f"Samples: {result['samples_output']}")
    print(f"Outputs: {result['outputs_output']}")
