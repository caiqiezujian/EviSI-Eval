"""Display v2.0.5 extraction focused on health_002 S3 (the people/COVID issue)."""
import json
from pathlib import Path

p = Path("results/entity_extraction_v2.0.5_smoke/results.jsonl")
with p.open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        print(f"=== {r['vid']} ===")
        for s in r["extraction"]["source_sentences"]:
            sid = s["sentence_id"]
            txt = s["text"]
            if len(txt) > 100:
                txt = txt[:100] + "..."
            print(f"  [{sid}] {txt}")
            for e in s["entities"]:
                print(f"      - {e}")
        print()