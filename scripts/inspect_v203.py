import json
from pathlib import Path

p = Path("results/entity_extraction_v2.0.3_smoke/results.jsonl")
with p.open(encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i >= 1:
            break
        r = json.loads(line)
        print("vid:", r["vid"])
        for s in r["extraction"]["source_sentences"][:2]:
            sid = s["sentence_id"]
            txt = s["text"][:100]
            print(f"  [{sid}] {txt}")
            for e in s["entities"]:
                print(f"      - {e}")