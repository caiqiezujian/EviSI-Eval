from __future__ import annotations

import hashlib
import json
from typing import Any

from .llm_provider import LLMClient
from .models import FACT_TYPES


CARD_PROMPT_VERSION = "card_builder_v1.1"

CARD_SYSTEM_PROMPT = """You are the Evaluation Card Builder for a simultaneous-interpretation benchmark.

Your task is analysis, not scoring. Read the source transcript and optional offline translation, then decompose the source into independently verifiable evaluation items. The offline translation is only a target-language aid; the source transcript remains authoritative. You must never infer requirements from a tested system output.

Your work has two stages. Stage 1 extracts sentence-level entity anchors. Stage 2 extracts propositions, relations, terminology, allowed_omissions, and forbidden_losses. Do BOTH in a single JSON output.

===== STAGE 1: Sentence-level entity extraction =====

输入文本通常不是单句，而是一段短篇章，至少包含几句话。因此你不能只输出全文级别的去重实体列表，而必须按照"句子级实体出现项"进行抽取。也就是说，每一个实体都必须标明它来自源文的哪一句。即使同一个实体在多句话中重复出现，也要分别记录为不同的 occurrence，因为后续评分时需要判断该实体在对应句子或对应语义片段中是否被译文正确传达，不能因为它在译文后文中出现过，就认为前一句已经正确覆盖。

第一步，请先对 source_text 进行句子切分。句子切分应尽量尊重原文已有标点和语义边界。不要把一个完整句子随意拆成过细片段，也不要把多个明显独立的句子合并。对于口语文本，如果存在明显的断句、停顿或话题切换，也可以作为句子边界。每个句子编号为 S1、S2、S3，以此类推。

第二步，请在每个句子内部抽取实体。这里的"实体"不是狭义命名实体，也不是所有名词，而是指在同传质量评估中具有独立检查价值的词项或短语。实体应以词或短语为单位，主要包括：

人名、机构名、国家、地区、城市、地点、产品名、项目名、政策名、会议名、事件名、法律法规名、疾病名、技术术语、专业概念、关键名词短语、时间表达、日期、年份、数量、金额、比例、排名、时长、频率、度量单位等。

请不要抽取没有独立评分价值的普通功能词、语气词、填充词、泛泛的代词、孤立形容词、孤立副词、普通动词。也不要把行为本身拆成过细的谓词标签。本阶段只抽取实体锚点，不抽取"谁做了什么"的行为结构。

对于"合作、竞争、支持、反对、增长、下降、改革、协议、计划、项目、政策、战略、机制、风险、成本、收益"等词，需要根据上下文判断。如果它们只是单独作为动作或行为关系出现，不要在实体层把它们抽成行为项；如果它们在句中构成名词性概念、术语、关键议题或可被翻译检查的词项，例如"战略合作""市场竞争""支持计划""改革方案""风险管理机制""成本压力"，则可以作为实体抽取。

实体抽取粒度要求如下：

命名实体应保持完整，不要拆开。例如 "New York Times" 应作为一个实体，不要拆成 "New York" 和 "Times"，除非上下文确实分别谈论地点和机构。

数字实体应尽量保留数字和单位。例如 "15 percent""3 million people""two years""2024" 都应作为完整实体。

时间实体应保留完整时间表达。例如 "last year""on Monday""in the first quarter of 2025" 不要拆得过细。

术语和关键概念应保留完整短语。例如 "carbon neutrality""supply chain resilience""artificial intelligence model" 不要只抽其中一个普通词。

同一个实体在同一句中重复出现，如果只是口语重复或无新增信息，可以只保留一次；如果在不同句子中出现，必须分别保留。

如果某一句中的代词明显指代前文核心实体，并且该指代对后续翻译评分有价值，可以抽取该代词出现项，并在 normalized_entity 中写出它指代的实体；但不要把普通无关代词都当作实体。

每个实体出现项必须包含以下字段：

occurrence_id：实体出现项编号，格式为 E1、E2、E3。
sentence_id：该实体来自哪一句，例如 S1、S2。
sentence_text：该实体所在的完整源文句子。
entity_text：实体在原文中的表面形式，必须尽量使用原文原词或原短语。
normalized_entity：规范化实体名称。如果不需要规范化，则与 entity_text 相同。如果是代词或简称，应写出它指代或对应的完整实体。
entity_type：实体类型，只能从以下类型中选择：PERSON、ORG、GPE、LOCATION、TIME、DATE、NUMBER、MONEY、PERCENT、PRODUCT、EVENT、LAW_POLICY、PROJECT、TECH_TERM、DOMAIN_TERM、KEY_CONCEPT、OTHER。
importance：实体重要性，只能取 high、medium、low。high 表示该实体对句子核心意思或事实判断非常重要；medium 表示该实体对理解有帮助但不是最核心；low 表示该实体属于背景性、修饰性或可弱化信息。
is_score_anchor：是否建议作为后续打分锚点，取 true 或 false。只有对同传译文质量判断有实际价值的实体才设为 true。
role_hint：该实体在句子中的大致作用，只能从以下类型中选择：subject、object、time、place、quantity、topic、term、modifier、reference、other。注意这只是辅助角色提示，不是行为分析。
extraction_reason：简短说明为什么抽取该实体，尤其说明它为什么对后续同传质量评估有价值。

===== STAGE 2: Proposition, relation, terminology, allowed_omission, forbidden_loss =====

propositions: atomic main meanings. Exclude fact values already represented in Stage 1 entities; link them with linked_entities (each entry references an occurrence_id from Stage 1).
relations: only meaning-bearing links between propositions. Allowed types: cause, condition, contrast, concession, comparison, purpose, temporal_order, exception, attribution, enumeration.
terminology: source terms and acceptable target-language candidates.
allowed_omissions: fillers, abandoned false starts, low-information repetition, or procedural padding that may be omitted.
forbidden_losses: facts, propositions, or relations whose loss changes conclusion, action, risk, eligibility, or speaker stance. kind must be "entity" / "proposition" / "relation"; ref_id must reference the corresponding E1 / p_001 / r_001.

Importance is deterministic in meaning (numeric 1/2/3):
3 = changes identity, conclusion, action, risk, legal/medical/financial meaning, threshold, or eligibility.
2 = important support or constraint.
1 = background detail.

Every source_span, sentence_text, and source_cue must be copied verbatim from the transcript. Do not output a score or deduction. Do not treat fluency or style as source meaning. Return JSON only.

===== Hard rules (apply to both stages) =====

- Do not extract behavior propositions in Stage 1. Stage 1 extracts entity anchors only.
- Do not judge the SI translation. You never see it.
- global_entity_inventory is an auxiliary index for human inspection. It must NEVER be used as a substitute for sentence-level entity_occurrences when scoring.
- If a sentence has no score-worthy entity, output entity_occurrences as an empty array.
- Better to extract fewer entities with real evaluation value than to dump every noun.
- linked_entities in propositions must reference existing occurrence_ids.
- forbidden_losses ref_id must reference an existing entity_occurrence / proposition / relation.

===== Required output shape =====

{
  "doc_id": "<doc_id or empty>",
  "sentences": [
    {
      "sentence_id": "S1",
      "sentence_text": "<verbatim sentence>",
      "entity_occurrences": [
        {
          "occurrence_id": "E1",
          "sentence_id": "S1",
          "sentence_text": "<same verbatim sentence>",
          "entity_text": "<surface form from source>",
          "normalized_entity": "<canonical form, or entity_text if no normalization>",
          "entity_type": "<PERSON|ORG|GPE|LOCATION|TIME|DATE|NUMBER|MONEY|PERCENT|PRODUCT|EVENT|LAW_POLICY|PROJECT|TECH_TERM|DOMAIN_TERM|KEY_CONCEPT|OTHER>",
          "importance": "high|medium|low",
          "is_score_anchor": true|false,
          "role_hint": "subject|object|time|place|quantity|topic|term|modifier|reference|other",
          "extraction_reason": "<why this entity matters for SI evaluation>"
        }
      ]
    }
  ],
  "global_entity_inventory": [
    {
      "normalized_entity": "<canonical form>",
      "entity_type": "<type>",
      "occurs_in_sentences": ["S1"],
      "occurrence_ids": ["E1"],
      "note": "Auxiliary index only. Do NOT use as primary scoring source."
    }
  ],
  "propositions": [
    {
      "prop_id": "p_001",
      "source_span": "<verbatim from transcript>",
      "canonical_meaning": "...",
      "target_reference": "<optional>",
      "importance": 1|2|3,
      "required": true|false,
      "linked_entities": ["E1", "E3"],
      "notes": "...",
      "extraction_confidence": 0.0-1.0
    }
  ],
  "relations": [
    {
      "relation_id": "r_001",
      "type": "<allowed relation type>",
      "source_cues": ["<verbatim cue>"],
      "head_prop_id": "p_001",
      "dependent_prop_id": "p_002",
      "canonical_meaning": "...",
      "importance": 1|2|3,
      "extraction_confidence": 0.0-1.0
    }
  ],
  "terminology": [
    {
      "term_id": "t_001",
      "source_term": "...",
      "target_candidates": ["..."],
      "importance": 1|2|3,
      "required": true|false
    }
  ],
  "allowed_omissions": [{"source_span": "...", "reason": "..."}],
  "forbidden_losses": [{"kind": "entity|proposition|relation", "ref_id": "E1|p_001|r_001", "reason": "..."}]
}

Return JSON only. No commentary, no Markdown, no code fence."""


def build_agent_card(sample: dict[str, Any], client: LLMClient) -> dict[str, Any]:
    transcript = str(sample.get("transcript") or sample.get("source_text") or "").strip()
    if not transcript:
        raise ValueError("Each sample must include a non-empty transcript or source_text")
    sample_id = str(sample.get("sample_id") or "").strip()
    if not sample_id:
        raise ValueError("Each sample must include sample_id")

    payload = {
        "task": "build_evaluation_card",
        "sample_id": sample_id,
        "transcript": transcript,
        "offline_translation": sample.get("offline_translation"),
        "src_lang": sample.get("src_lang", "unspecified"),
        "tgt_lang": sample.get("tgt_lang", "unspecified"),
        "domain": sample.get("domain", "unspecified"),
    }
    response = client.generate_json(CARD_SYSTEM_PROMPT, payload, task="build_evaluation_card")
    raw_card = response.data.get("evaluation_card", response.data)
    if not isinstance(raw_card, dict):
        raise ValueError("Card builder response must contain a JSON object")
    card, issues = normalize_card(raw_card, sample)
    card["metadata"] = {
        "schema_version": "1.1.0",
        "prompt_version": CARD_PROMPT_VERSION,
        "builder_provider": response.provider,
        "builder_model": response.model,
        "builder_request_id": response.request_id,
        "card_status": "draft",
        "review_required": bool(issues),
        "validation_issues": issues,
        "system_outputs_visible_to_builder": False,
    }
    card["metadata"]["card_hash"] = card_hash(card)
    return card


def normalize_card(raw: dict[str, Any], sample: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    transcript = str(sample.get("transcript") or sample.get("source_text") or "").strip()
    issues: list[str] = []

    raw_sentences = _list(raw.get("sentences"))
    use_occurrence_layout = bool(raw_sentences)

    facts: list[dict[str, Any]] = []
    if use_occurrence_layout:
        for sentence in raw_sentences:
            sentence_id = str(sentence.get("sentence_id") or "").strip()
            sentence_text = str(sentence.get("sentence_text") or "").strip()
            for occ_index, item in enumerate(_list(sentence.get("entity_occurrences")), 1):
                entity_type = str(item.get("entity_type") or "OTHER").strip().upper()
                if entity_type not in _ENTITY_TYPES:
                    issues.append(
                        f"{sentence_id}/entity_occurrences[{occ_index}] unsupported entity_type={entity_type!r}; normalized to OTHER"
                    )
                    entity_type = "OTHER"
                entity_text = str(item.get("entity_text") or "").strip()
                if not entity_text:
                    issues.append(f"{sentence_id}/entity_occurrences[{occ_index}] missing entity_text; item dropped")
                    continue
                if sentence_text and entity_text not in sentence_text:
                    issues.append(
                        f"{sentence_id}/entity_occurrences[{occ_index}] entity_text not found in sentence_text"
                    )
                if entity_text not in transcript:
                    issues.append(
                        f"{sentence_id}/entity_occurrences[{occ_index}] entity_text not found in transcript"
                    )
                semantic_importance = _semantic_importance(item.get("importance"))
                numeric_importance = _semantic_to_numeric(semantic_importance)
                is_anchor = bool(item.get("is_score_anchor", semantic_importance != "low"))
                facts.append(
                    {
                        "fact_id": str(item.get("occurrence_id") or f"E_{sentence_id}_{occ_index}"),
                        "type": entity_type.lower(),
                        "entity_type": entity_type,
                        "sentence_id": sentence_id,
                        "sentence_text": sentence_text,
                        "source_span": entity_text,
                        "canonical_value": str(item.get("normalized_entity") or entity_text),
                        "normalized_entity": str(item.get("normalized_entity") or entity_text),
                        "importance": semantic_importance,
                        "importance_numeric": numeric_importance,
                        "must_preserve": bool(item.get("must_preserve", is_anchor)),
                        "is_score_anchor": is_anchor,
                        "role_hint": str(item.get("role_hint") or "other").strip().lower(),
                        "acceptable_variants": _strings(item.get("acceptable_variants")),
                        "notes": _optional_string(item.get("extraction_reason"))
                        or _optional_string(item.get("notes")),
                        "extraction_confidence": _confidence(item.get("extraction_confidence"), 0.8),
                    }
                )
        facts = _dedupe_ids(facts, "fact_id", "E")
    else:
        for index, item in enumerate(_list(raw.get("facts")), 1):
            fact_type = str(item.get("type") or "term").strip().lower()
            if fact_type not in FACT_TYPES:
                issues.append(f"facts[{index}] has unsupported type={fact_type!r}; normalized to term")
                fact_type = "term"
            source_span = str(item.get("source_span") or "").strip()
            if not source_span:
                issues.append(f"facts[{index}] missing source_span; item dropped")
                continue
            if source_span not in transcript:
                issues.append(f"facts[{index}] source_span is not verbatim transcript text")
            numeric_importance = _importance(item.get("importance"))
            facts.append(
                {
                    "fact_id": str(item.get("fact_id") or f"f_{index:03d}"),
                    "type": fact_type,
                    "entity_type": fact_type.upper(),
                    "sentence_id": "",
                    "sentence_text": "",
                    "source_span": source_span,
                    "canonical_value": item.get("canonical_value", source_span),
                    "normalized_entity": str(item.get("canonical_value") or source_span),
                    "importance": _numeric_to_semantic(numeric_importance),
                    "importance_numeric": numeric_importance,
                    "must_preserve": bool(item.get("must_preserve", numeric_importance >= 2)),
                    "is_score_anchor": bool(item.get("must_preserve", numeric_importance >= 2)),
                    "role_hint": "other",
                    "acceptable_variants": _strings(item.get("acceptable_variants")),
                    "notes": _optional_string(item.get("notes")),
                    "extraction_confidence": _confidence(item.get("extraction_confidence"), 0.8),
                }
            )
        facts = _dedupe_ids(facts, "fact_id", "f")
    fact_ids = {item["fact_id"] for item in facts}

    propositions: list[dict[str, Any]] = []
    for index, item in enumerate(_list(raw.get("propositions")), 1):
        source_span = str(item.get("source_span") or "").strip()
        if not source_span:
            issues.append(f"propositions[{index}] missing source_span; item dropped")
            continue
        if source_span not in transcript:
            issues.append(f"propositions[{index}] source_span is not verbatim transcript text")
        linked_entities = [x for x in _strings(item.get("linked_entities")) if x in fact_ids]
        linked_facts = [x for x in _strings(item.get("linked_facts")) if x in fact_ids]
        propositions.append(
            {
                "prop_id": str(item.get("prop_id") or f"p_{index:03d}"),
                "source_span": source_span,
                "canonical_meaning": str(item.get("canonical_meaning") or source_span).strip(),
                "target_reference": _optional_string(item.get("target_reference")),
                "importance": _importance(item.get("importance")),
                "required": bool(item.get("required", True)),
                "linked_entities": linked_entities,
                "linked_facts": linked_entities or linked_facts,
                "notes": _optional_string(item.get("notes")),
                "extraction_confidence": _confidence(item.get("extraction_confidence"), 0.8),
            }
        )
    if not propositions:
        issues.append("No proposition returned; inserted one document-level proposition for mandatory review")
        propositions = [
            {
                "prop_id": "p_001",
                "source_span": transcript,
                "canonical_meaning": str(sample.get("offline_translation") or transcript),
                "target_reference": _optional_string(sample.get("offline_translation")),
                "importance": 3,
                "required": True,
                "linked_entities": sorted(fact_ids),
                "linked_facts": sorted(fact_ids),
                "notes": "Fallback item because the card model returned no propositions",
                "extraction_confidence": 0.0,
            }
        ]
    propositions = _dedupe_ids(propositions, "prop_id", "p")
    prop_ids = {item["prop_id"] for item in propositions}

    relations: list[dict[str, Any]] = []
    for index, item in enumerate(_list(raw.get("relations")), 1):
        head = str(item.get("head_prop_id") or "")
        dependent = str(item.get("dependent_prop_id") or "")
        if head not in prop_ids or dependent not in prop_ids:
            issues.append(f"relations[{index}] references unknown propositions; item dropped")
            continue
        cues = _strings(item.get("source_cues"))
        if any(cue not in transcript for cue in cues):
            issues.append(f"relations[{index}] includes a non-verbatim source cue")
        relations.append(
            {
                "relation_id": str(item.get("relation_id") or f"r_{index:03d}"),
                "type": str(item.get("type") or "unspecified").strip().lower(),
                "source_cues": cues,
                "head_prop_id": head,
                "dependent_prop_id": dependent,
                "canonical_meaning": str(item.get("canonical_meaning") or "").strip(),
                "importance": _importance(item.get("importance")),
                "extraction_confidence": _confidence(item.get("extraction_confidence"), 0.8),
            }
        )
    relations = _dedupe_ids(relations, "relation_id", "r")

    terminology = []
    for index, item in enumerate(_list(raw.get("terminology")), 1):
        source_term = str(item.get("source_term") or "").strip()
        if not source_term:
            continue
        terminology.append(
            {
                "term_id": str(item.get("term_id") or f"t_{index:03d}"),
                "source_term": source_term,
                "target_candidates": _strings(item.get("target_candidates")),
                "importance": _importance(item.get("importance")),
                "required": bool(item.get("required", True)),
            }
        )

    card = {
        "sample_id": str(sample["sample_id"]),
        "transcript": transcript,
        "source_text": transcript,
        "offline_translation": sample.get("offline_translation"),
        "domain": sample.get("domain", "unspecified"),
        "src_lang": sample.get("src_lang", "unspecified"),
        "tgt_lang": sample.get("tgt_lang", "unspecified"),
        "facts": facts,
        "propositions": propositions,
        "relations": relations,
        "terminology": terminology,
        "allowed_omissions": _simple_records(raw.get("allowed_omissions"), "source_span", "reason"),
        "forbidden_losses": _simple_records(raw.get("forbidden_losses"), "kind", "ref_id", "reason"),
    }
    if use_occurrence_layout:
        normalized_sentences = []
        for sentence in raw_sentences:
            normalized_sentences.append(
                {
                    "sentence_id": str(sentence.get("sentence_id") or "").strip(),
                    "sentence_text": str(sentence.get("sentence_text") or "").strip(),
                    "entity_occurrences": _list(sentence.get("entity_occurrences")),
                }
            )
        card["sentences"] = normalized_sentences
        card["entity_occurrences"] = [
            occ for sentence in normalized_sentences for occ in _list(sentence.get("entity_occurrences"))
        ]
        card["global_entity_inventory"] = _simple_records(
            raw.get("global_entity_inventory"),
            "normalized_entity",
            "entity_type",
            "occurs_in_sentences",
            "occurrence_ids",
            "note",
        )
    return card, issues


def card_hash(card: dict[str, Any]) -> str:
    payload = {key: value for key, value in card.items() if key != "metadata"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _importance(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 2
    return min(3, max(1, parsed))


def _confidence(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return round(min(1.0, max(0.0, parsed)), 4)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dedupe_ids(items: list[dict[str, Any]], key: str, prefix: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    for index, item in enumerate(items, 1):
        item_id = str(item.get(key) or f"{prefix}_{index:03d}")
        if item_id in seen:
            item_id = f"{prefix}_{index:03d}"
        item[key] = item_id
        seen.add(item_id)
    return items


def _simple_records(value: Any, *keys: str) -> list[dict[str, Any]]:
    records = []
    for item in _list(value):
        record = {key: item.get(key) for key in keys}
        if any(v is not None and v != "" for v in record.values()):
            records.append(record)
    return records


_ENTITY_TYPES = {
    "PERSON",
    "ORG",
    "GPE",
    "LOCATION",
    "TIME",
    "DATE",
    "NUMBER",
    "MONEY",
    "PERCENT",
    "PRODUCT",
    "EVENT",
    "LAW_POLICY",
    "PROJECT",
    "TECH_TERM",
    "DOMAIN_TERM",
    "KEY_CONCEPT",
    "OTHER",
}


def _semantic_importance(value: Any) -> str:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"high", "h", "3"}:
            return "high"
        if lowered in {"medium", "med", "mid", "2"}:
            return "medium"
        if lowered in {"low", "l", "1"}:
            return "low"
    if isinstance(value, (int, float)):
        return _numeric_to_semantic(int(value))
    return "medium"


def _semantic_to_numeric(value: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(value, 2)


def _numeric_to_semantic(value: int) -> str:
    return {3: "high", 2: "medium", 1: "low"}.get(value, "medium")
