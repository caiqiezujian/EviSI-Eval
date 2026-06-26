#!/usr/bin/env python
from __future__ import annotations

import argparse

from evisi_eval.pipeline import print_summary, run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="EviSI-Eval benchmark pipeline")
    parser.add_argument("--samples", default="data/mode_demo_raw_samples.jsonl", help="Transcript sample JSONL")
    parser.add_argument("--outputs", default="data/mode_demo_system_outputs.jsonl", help="System output JSONL")
    parser.add_argument("--output-dir", default="results", help="Benchmark output directory")
    parser.add_argument("--run-name", default="mode_demo", help="Run name under output-dir")
    parser.add_argument("--skip-card-build", action="store_true", help="Reuse existing cards for this run")
    args = parser.parse_args()

    metrics = run_pipeline(
        samples_path=args.samples,
        outputs_path=args.outputs,
        output_dir=args.output_dir,
        run_name=args.run_name,
        skip_card_build=args.skip_card_build,
    )
    print_summary(metrics)


if __name__ == "__main__":
    main()

