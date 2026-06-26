# Fact Review Prompt

You verify whether a proposed error is valid.

Answer with JSON only:

```json
{
  "review": "valid | invalid | uncertain",
  "confidence": 0.0,
  "reason": "short evidence-based reason"
}
```

Do not rescore the translation. Only decide whether the proposed local error is real.

