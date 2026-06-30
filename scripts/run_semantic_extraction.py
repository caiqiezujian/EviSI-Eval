"""Run only source extraction, alignment, and target semantic extraction."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from evisi_eval.extraction_pipeline import run_extraction_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract source/target Anchor, Event, and conservative Relation cards only."
    )
    parser.add_argument("--samples", required=True)
    parser.add_argument("--outputs", required=True)
    parser.add_argument("--output-dir", default="results")
    parser.add_argument("--run-name", default="semantic_extraction")
    parser.add_argument("--provider", default="deepseek", choices=["deepseek", "openai", "gemini", "custom"])
    parser.add_argument("--limit-samples", type=int)
    parser.add_argument("--limit-outputs", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    summary = run_extraction_pipeline(
        samples_path=args.samples,
        outputs_path=args.outputs,
        output_dir=args.output_dir,
        run_name=args.run_name,
        provider_name=args.provider,
        resume=args.resume,
        limit_samples=args.limit_samples,
        limit_outputs=args.limit_outputs,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
