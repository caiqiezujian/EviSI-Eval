# Target Delivery Evaluator v0.4

Evaluate only target-language delivery in an anonymous final simultaneous-interpretation translation. Do not evaluate source fidelity here. Reasonable compression, ordinary spoken syntax, and concise reformulation are acceptable.

Fluency issue types: grammar_error, sentence_fragment, source_language_residue, unnatural_collocation, unclear_reference, register_mismatch, unintelligible_segment.
Efficiency issue types: meaningless_repetition, redundant_restatement, excessive_filler, unsupported_addition, avoidable_verbosity.

Conciseness is not a length ratio. Do not penalize necessary explanation, valid reformulation, or repetitions that carry new information. An unsupported addition must be a concrete target claim, not merely different wording.

Each issue must cite a contiguous verbatim target_span and severity minor, major, or critical. Return empty arrays when no concrete issue exists. Do not score.

{"fluency_issues":[{"issue_id":"F1","issue_type":"grammar_error","target_span":"verbatim","severity":"minor","confidence":0.0,"reason":"...","listener_impact":"..."}],"efficiency_issues":[{"issue_id":"Q1","issue_type":"meaningless_repetition","target_span":"verbatim","severity":"minor","confidence":0.0,"reason":"...","listener_impact":"..."}]}

Return JSON only.
