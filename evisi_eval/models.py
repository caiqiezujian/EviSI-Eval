from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


FACT_TYPES = {
    "number",
    "percentage",
    "money",
    "unit",
    "date_time",
    "entity",
    "term",
    "polarity",
    "direction",
    "scope",
    "modality",
}


@dataclass
class Fact:
    fact_id: str
    type: str
    source_span: str
    canonical_value: Any
    importance: int = 2
    must_preserve: bool = True
    acceptable_variants: list[str] = field(default_factory=list)
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvaluationCard:
    sample_id: str
    source_text: str
    offline_translation: str | None = None
    domain: str = "unspecified"
    src_lang: str = "en"
    tgt_lang: str = "zh"
    facts: list[Fact] = field(default_factory=list)
    propositions: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    terminology: list[dict[str, Any]] = field(default_factory=list)
    allowed_omissions: list[dict[str, Any]] = field(default_factory=list)
    forbidden_losses: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["facts"] = [fact.to_dict() for fact in self.facts]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvaluationCard":
        facts = [Fact(**item) for item in data.get("facts", [])]
        return cls(
            sample_id=data["sample_id"],
            source_text=data["source_text"],
            offline_translation=data.get("offline_translation"),
            domain=data.get("domain", "unspecified"),
            src_lang=data.get("src_lang", "en"),
            tgt_lang=data.get("tgt_lang", "zh"),
            facts=facts,
            propositions=data.get("propositions", []),
            relations=data.get("relations", []),
            terminology=data.get("terminology", []),
            allowed_omissions=data.get("allowed_omissions", []),
            forbidden_losses=data.get("forbidden_losses", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class FactVerdict:
    fact_id: str
    type: str
    source_span: str
    canonical_value: Any
    importance: int
    must_preserve: bool
    translation_span: str | None
    normalized_translation_value: Any
    verdict: str
    confidence: float
    deduction: float
    severity: str
    evidence_text: str
    reason: str
    review_required: bool = False
    cap_trigger: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

