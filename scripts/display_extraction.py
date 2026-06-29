"""Display extracted sentences + entities per sample for review."""
import json
from pathlib import Path

rows = [json.loads(l) for l in Path("results/entity_extraction_v2_smoke/results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
for r in rows:
    print(f"=== {r['vid']} ===")
    if "error" in r:
        print(f"  ERROR: {r['error']}")
        continue
    for s in r["extraction"]["source_sentences"]:
        text = s["text"]
        if len(text) > 100:
            text = text[:100] + "..."
        print(f"  [{s['sentence_id']}] {text}")
        for e in s["entities"]:
            print(f"      - {e}")
    if r.get("validation_issues"):
        print(f"  [validation issues]")
        for iss in r["validation_issues"]:
            print(f"      ! {iss}")
    print()