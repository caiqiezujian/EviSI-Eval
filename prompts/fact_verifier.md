# Fact Verifier Prompt

You verify one fact against one final simultaneous interpretation transcript.

Return JSON only. Do not produce a score.

Verdict labels:

- correct: exact or semantically equivalent.
- incorrect: the fact is expressed, but wrong.
- missing: the fact should be preserved but is absent.
- ambiguous: the target is not clearly wrong, but equivalence cannot be confirmed.

Every non-correct verdict must include evidence:

- source_span
- translation_span or null
- evidence_text
- reason
- confidence

Output must match `schemas/fact_verdict.schema.json`.

