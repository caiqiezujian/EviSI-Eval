"""Display extraction from v2.0.3 output."""
import json
from pathlib import Path

p = Path("results/entity_extraction_v2.0.3_smoke/results.jsonl")
rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
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
    print()