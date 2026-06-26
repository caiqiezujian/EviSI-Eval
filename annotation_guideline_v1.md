# EviSI-Eval Annotation Guideline v1

This guideline is for v0.1 card review. Human reviewers check the Evaluation Card, not the final system score.

## Scope

v0.1 only covers key facts:

- numbers and percentages
- money
- date/time
- entities and terms
- polarity
- direction
- scope
- modality

Do not add general fluency, style, delivery, or latency comments to `facts[]`.

## Importance

Use `importance = 3` when a fact error would change:

- subject or object identity
- conclusion or stance
- action requirement
- legal, medical, financial, engineering, or safety risk
- deadline, threshold, or eligibility boundary

Use `importance = 2` when the fact is important support but not decisive.

Use `importance = 1` when the fact is background detail.

When unsure, ask: would a listener make a different decision if this fact was wrong? If yes, use `3`.

## Attribution Priority

Each error should be penalized once, in this order:

1. fact accuracy
2. core proposition coverage
3. logic relation preservation
4. SI expression adaptability
5. target-language acceptability

For v0.1, only fact accuracy is active. Later dimensions must not re-penalize the same fact error.

## Allowed Omissions

Usually allowed:

- fillers such as "you know", "I mean", "basically"
- false starts
- low-information repetition
- greeting or procedural padding that does not affect meaning

Never mark as allowed omission:

- number, amount, threshold, percentage
- negation, exception, condition, deadline
- conclusion, action item, legal or medical constraint
- subject or object identity

## Card Review Checklist

- Are all high-risk facts present?
- Are duplicate facts removed?
- Are `acceptable_variants` sufficient for Chinese equivalents and aliases?
- Are all `importance=3` facts also `must_preserve=true`?
- Are `allowed_omissions` and `forbidden_losses` aligned with the source?
- Is the card independent from a specific system output?

