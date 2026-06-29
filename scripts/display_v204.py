"""Display v2.0.4 extraction."""
import json
from pathlib import Path

p = Path("results/entity_extraction_v2.0.4_smoke/results.jsonl")
with p.open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        print(f"=== {r['vid']} ===")
        for s in r["extraction"]["source_sentences"]:
            txt = s["text"]
            if len(txt) > 100:
                txt = txt[:100] + "..."
            print(f"  [{s['sentence_id']}] {txt}")
            for e in s["entities"]:
                print(f"      - {e}")
        print()