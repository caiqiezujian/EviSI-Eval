"""Extract Joint Card (Anchor/Event/Relation) for a single sample.

Usage:
  python scripts/extract_joint_card.py \\
    --sample data/user_samples_v03/samples/en2zh-01-tech_001/source.json \\
    --output results/extraction_check/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evisi_eval.config import get_provider_config
from evisi_eval.llm_provider import HTTPJSONClient
from evisi_eval.v07_agents import V07JointCardBuilder


def main():
    parser = argparse.ArgumentParser(description="Extract v0.7 Joint Card from a sample")
    parser.add_argument("--sample", required=True, help="Path to source.json")
    parser.add_argument("--output", default="results/extraction_check", help="Output directory")
    parser.add_argument("--provider", default="deepseek", help="Provider name")
    args = parser.parse_args()

    # Load sample
    sample = json.loads(Path(args.sample).read_text(encoding="utf-8"))
    sample_id = sample["sample_id"]
    print(f"Sample: {sample_id}")
    print(f"Source length: {len(sample['source_text'])} chars")
    print(f"Reference length: {len(sample['reference_translation'])} chars")
    print(f"Provider: {args.provider}")

    # Setup
    config = get_provider_config(args.provider)
    print(f"Model: {config.model}")
    client = HTTPJSONClient(config)

    out_dir = Path(args.output) / sample_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build Joint Card (8 LLM calls)
    builder = V07JointCardBuilder(client)
    print("\n--- Phases 1-8: Building Joint Card ---")

    try:
        joint_card, stage_results = builder.build(
            sample,
            stage_cache_dir=str(out_dir / "stages"),
            resume=False,
        )
    except Exception as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)

    # ── Write outputs ──────────────────────────────────────────

    # Full joint card
    joint_path = out_dir / "joint_card.json"
    joint_path.write_text(
        json.dumps(joint_card, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nJoint Card → {joint_path}")

    # Per-stage results (human-readable)
    stages_dir = out_dir / "stages"
    stages_dir.mkdir(parents=True, exist_ok=True)

    stage_names = [
        "01_source_segments",
        "02_source_anchors",
        "03_source_events",
        "04_source_relations",
        "05_reference_segments",
        "06_reference_anchors",
        "07_reference_events",
        "08_reference_relations",
    ]

    for i, (sr, name) in enumerate(zip(stage_results, stage_names)):
        stage_path = stages_dir / f"{name}.json"
        stage_path.write_text(
            json.dumps(sr.artifact, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        status = "✓" if sr.validated else "✗ (used fallback)" if sr.fallback_used else "✗"
        print(f"  Phase {i+1} {name}: {status} (repairs={sr.repair_attempts})")

    # ── Summary ─────────────────────────────────────────────────
    print(f"\n=== Extraction Summary for {sample_id} ===")
    segs = joint_card.get("segments", [])
    print(f"Segments: {len(segs)}")

    flat_anchors = joint_card.get("flat_anchors", [])
    flat_events = joint_card.get("flat_events", [])
    flat_relations = joint_card.get("flat_relations", [])
    print(f"Anchors:  {len(flat_anchors)}")
    print(f"Events:   {len(flat_events)}")
    print(f"Relations:{len(flat_relations)}")

    # Type breakdown
    from collections import Counter
    anchor_types = Counter(a.get("type") for a in flat_anchors)
    event_types = Counter(e.get("type") for e in flat_events)
    relation_types = Counter(r.get("type") for r in flat_relations)
    print(f"Anchor types:  {dict(anchor_types)}")
    print(f"Event types:   {dict(event_types)}")
    print(f"Relation types:{dict(relation_types)}")

    # Per-segment detail
    print("\n--- Per Segment ---")
    for seg in segs:
        sid = seg["seg_id"]
        print(f"\n[{sid}] {seg['source_text'][:100]}...")
        print(f"  Ref: {seg['reference_text'][:80]}...")
        for a in seg.get("anchors", []):
            print(f"  Anchor [{a['type']}] {a['source_text']} → {a['reference_text']} (imp={a['importance']})")
        for e in seg.get("events", []):
            print(f"  Event [{e['type']}] {e['source_summary']} → {e.get('reference_summary', 'N/A')} (imp={e['importance']})")
    for r in flat_relations:
        print(f"  Relation [{r['type']}]: {r.get('source_summary', r.get('summary', 'N/A'))} (imp={r['importance']})")

    print(f"\nAll results saved to: {out_dir}")


if __name__ == "__main__":
    main()
