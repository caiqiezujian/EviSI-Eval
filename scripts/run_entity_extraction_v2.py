"""
Run v2.0 entity extraction prompt on raw_data.jsonl via DeepSeek.

Design principle (v2.0.3+): the LLM owns ALL judgment about extraction
quality. Python only handles I/O, orchestration, failure isolation, and
the run manifest. There are no Python-side regular expressions or string
matchers checking whether an entity is "verbatim" — that contract is
enforced inside the prompt itself.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# --- Load v2.0 prompt from prompts/entity_extractor_v2.0_draft.md ---
PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "entity_extractor_v2.0_draft.md"
prompt_text = PROMPT_PATH.read_text(encoding="utf-8")

# --- DeepSeek config ---
API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
# Default: DeepSeek-V4-Pro (released 2026-04-24, 1.6T/49B MoE, 1M context).
# V3.x → V4 migration: existing deepseek-chat / deepseek-reasoner endpoints
# will be phased out within 3 months. For rule-based structured extraction,
# V4-Pro gives better JSON-schema adherence than R1, and is cheaper/faster.
# Override via env var: DEEPSEEK_MODEL=deepseek-reasoner python ...
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
BASE_URL = "https://api.deepseek.com"


def call_deepseek(system_prompt: str, user_payload: dict, task: str) -> dict:
    url = f"{BASE_URL}/chat/completions"
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
    last_error = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, data=encoded,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                response = json.loads(resp.read().decode("utf-8"))
            content = response["choices"][0]["message"]["content"]
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                txt = content.strip()
                if txt.startswith("```"):
                    lines = txt.splitlines()
                    if lines and lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    txt = "\n".join(lines).strip()
                start = txt.find("{")
                end = txt.rfind("}")
                if start >= 0 and end > start:
                    return json.loads(txt[start:end + 1])
                raise ValueError(f"Cannot parse JSON from response: {content[:200]}")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
            last_error = e
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"{task} failed after retries: {last_error}")


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if not API_KEY:
        print("ERROR: DEEPSEEK_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    input_path = Path("data/raw_data.jsonl")
    samples = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"loaded {len(samples)} samples from {input_path}")

    # CLI args override defaults; default keeps backward-compat with prior runs.
    import sys
    if len(sys.argv) >= 3:
        out_dir = Path(sys.argv[1])
        run_label = sys.argv[2]
    else:
        out_dir = Path("results/entity_extraction_v2.0.3_smoke")
        run_label = "v2.0.3_smoke"
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.jsonl"
    manifest_path = out_dir / "run_manifest.json"
    print(f"output -> {out_dir}")

    results = []
    for i, sample in enumerate(samples, 1):
        vid = sample.get("vid", f"sample_{i}")
        transcript = sample.get("transcript", "")
        user_payload = {
            "doc_id": vid,
            "source_language": "en",
            "target_language": "zh",
            "source_text": transcript,
        }
        print(f"[{i}/{len(samples)}] {vid}: calling DeepSeek ({len(transcript)} chars)...")
        t0 = time.time()
        try:
            extraction = call_deepseek(prompt_text, user_payload, task=f"extract_{vid}")
            elapsed = time.time() - t0
            n_sentences = len(extraction.get("source_sentences", []))
            n_entities = sum(
                len(s.get("entities", []))
                for s in extraction.get("source_sentences", [])
            )
            row = {
                "vid": vid,
                "transcript_len": len(transcript),
                "elapsed_seconds": round(elapsed, 2),
                "source_sentence_count": n_sentences,
                "total_entities": n_entities,
                "extraction": extraction,
            }
            results.append(row)
            print(f"  OK | sentences={n_sentences} entities={n_entities} | {elapsed:.1f}s")
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({
                "vid": vid,
                "transcript_len": len(transcript),
                "error": str(e),
            })

    with results_path.open("w", encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    success_count = sum(1 for r in results if "extraction" in r)
    failed_count = sum(1 for r in results if "error" in r)
    manifest = {
        "model": MODEL,
        "prompt_version": run_label,
        "prompt_path": str(PROMPT_PATH),
        "input_path": str(input_path),
        "input_sha256": _file_hash(input_path),
        "sample_count": len(samples),
        "success_count": success_count,
        "failed_count": failed_count,
        "total_sentences": sum(r.get("source_sentence_count", 0) for r in results),
        "total_entities": sum(r.get("total_entities", 0) for r in results),
        "validation_strategy": "llm_self_enforced",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nmanifest: {json.dumps(manifest, ensure_ascii=False, indent=2)}")
    print(f"results: {results_path}")


if __name__ == "__main__":
    main()