from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


MONTHS = {
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
}

NEGATION_MARKERS = [
    "not",
    "no",
    "never",
    "fail to",
    "failed to",
    "without",
    "未",
    "不",
    "无",
    "没有",
    "不得",
    "并非",
]

DIRECTION_MAP = {
    "increase": "increase",
    "increased": "increase",
    "rise": "increase",
    "rose": "increase",
    "growth": "increase",
    "增长": "increase",
    "上升": "increase",
    "提高": "increase",
    "decrease": "decrease",
    "decreased": "decrease",
    "fall": "decrease",
    "fell": "decrease",
    "drop": "decrease",
    "dropped": "decrease",
    "下降": "decrease",
    "下跌": "decrease",
    "减少": "decrease",
    "approve": "approve",
    "approved": "approve",
    "获批": "approve",
    "批准": "approve",
    "reject": "reject",
    "rejected": "reject",
    "否决": "reject",
    "反对": "reject",
}

SCOPE_MAP = {
    "at least": "at_least",
    "至少": "at_least",
    "no less than": "at_least",
    "at most": "at_most",
    "最多": "at_most",
    "no more than": "at_most",
    "only": "only",
    "仅": "only",
    "只": "only",
    "all": "all",
    "所有": "all",
    "some": "some",
    "一些": "some",
    "except": "except",
    "除外": "except",
}

MODALITY_MAP = {
    "must": "must",
    "必须": "must",
    "should": "should",
    "应": "should",
    "应该": "should",
    "may": "may",
    "might": "may",
    "could": "may",
    "可以": "may",
    "可能": "may",
    "likely": "likely",
    "很可能": "likely",
    "prohibited": "prohibited",
    "禁止": "prohibited",
    "not required": "not_required",
    "无需": "not_required",
}

KNOWN_ENTITY_ALIASES = {
    "apple": ["Apple", "Apple Inc.", "苹果", "苹果公司"],
    "google": ["Google", "Google LLC", "谷歌", "谷歌公司"],
    "unitednations": ["United Nations", "UN", "联合国"],
    "nato": ["NATO", "北约"],
    "europeanunion": ["European Union", "EU", "欧盟"],
}


@dataclass
class Match:
    span: str
    value: Any
    start: int
    end: int


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_simple(text: str) -> str:
    return re.sub(r"[\W_]+", "", (text or "").casefold())


def normalize_number(raw: str) -> Decimal | None:
    value = raw.replace(",", "").strip()
    multiplier = Decimal(1)
    if value.lower().endswith("k"):
        multiplier = Decimal(1_000)
        value = value[:-1]
    elif value.lower().endswith("m"):
        multiplier = Decimal(1_000_000)
        value = value[:-1]
    elif value.lower().endswith("b"):
        multiplier = Decimal(1_000_000_000)
        value = value[:-1]
    try:
        return Decimal(value) * multiplier
    except InvalidOperation:
        return None


def find_percentages(text: str) -> list[Match]:
    matches: list[Match] = []
    for item in re.finditer(r"(?<![A-Za-z0-9_.])(\d+(?:,\d{3})*(?:\.\d+)?)\s*(%|percent|percentage points?)", text, re.I):
        number = normalize_number(item.group(1))
        if number is not None:
            matches.append(Match(item.group(0), {"number": str(number), "unit": "%"}, item.start(), item.end()))
    for item in re.finditer(r"百分之\s*([零一二三四五六七八九十百千万亿\d.]+)", text):
        matches.append(Match(item.group(0), {"surface": item.group(1), "unit": "%"}, item.start(), item.end()))
    return matches


def find_money(text: str) -> list[Match]:
    pattern = r"((?:USD|US\$|\$|EUR|€|GBP|£|人民币|RMB|CNY)\s*\d+(?:,\d{3})*(?:\.\d+)?\s*[kmbKMB]?|\d+(?:,\d{3})*(?:\.\d+)?\s*(?:million|billion|万元|亿元|美元|人民币|元))"
    return [Match(m.group(0), {"surface": m.group(0)}, m.start(), m.end()) for m in re.finditer(pattern, text, re.I)]


def find_numbers(text: str) -> list[Match]:
    occupied = [(m.start, m.end) for m in find_percentages(text) + find_money(text)]
    matches: list[Match] = []
    for item in re.finditer(r"(?<![A-Za-z0-9_.])\d+(?:,\d{3})*(?:\.\d+)?\s*[kmbKMB]?(?!\s*(%|percent|million|billion|美元|元))", text, re.I):
        if any(item.start() >= start and item.end() <= end for start, end in occupied):
            continue
        number = normalize_number(item.group(0))
        if number is not None:
            matches.append(Match(item.group(0), str(number), item.start(), item.end()))
    return matches


def find_dates(text: str) -> list[Match]:
    patterns = [
        r"\bQ[1-4]\b",
        r"\b(?:first|second|third|fourth) quarter\b",
        r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
        r"\b(?:by|before|after|until)\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\b",
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,\s*\d{4})?\b",
        r"\b20\d{2}\b",
        r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
        r"\b\d{1,2}\s*月\s*\d{0,2}\s*日?\b",
        r"\b\d{4}\s*年\b",
    ]
    matches: list[Match] = []
    for pattern in patterns:
        for item in re.finditer(pattern, text, re.I):
            matches.append(Match(item.group(0), normalize_simple(item.group(0)), item.start(), item.end()))
    return _dedupe_matches(matches)


def find_entities(text: str) -> list[Match]:
    pattern = r"\b(?:[A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+){0,4}|[A-Z]{2,})\b"
    stop = {
        "The", "A", "An", "I", "Q", "At", "By", "Before", "After", "Until", "If",
        "January", "February", "March", "April", "May", "June", "July", "August",
        "September", "October", "November", "December", "Monday", "Tuesday",
        "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    }
    matches: list[Match] = []
    for item in re.finditer(pattern, text):
        span = item.group(0)
        if span in stop or re.fullmatch(r"Q[1-4]", span):
            continue
        matches.append(Match(span, normalize_simple(span), item.start(), item.end()))
    for aliases in KNOWN_ENTITY_ALIASES.values():
        for alias in aliases:
            if re.search(r"[A-Za-z]", alias):
                continue
            for item in re.finditer(re.escape(alias), text):
                matches.append(Match(item.group(0), normalize_simple(alias), item.start(), item.end()))
    return _dedupe_matches(matches)


def variants_for_entity(span: str) -> list[str]:
    key = normalize_simple(span)
    return KNOWN_ENTITY_ALIASES.get(key, [span])


def variants_for_date(span: str) -> list[str]:
    key = normalize_simple(span)
    if key in {"q1", "firstquarter"}:
        return [span, "Q1", "first quarter", "第一季度", "一季度"]
    if key in {"q2", "secondquarter"}:
        return [span, "Q2", "second quarter", "第二季度", "二季度"]
    if key in {"q3", "thirdquarter"}:
        return [span, "Q3", "third quarter", "第三季度", "三季度"]
    if key in {"q4", "fourthquarter"}:
        return [span, "Q4", "fourth quarter", "第四季度", "四季度"]
    for month_en, month_num in MONTHS.items():
        month_cn = f"{int(month_num)}月"
        month_cn_alt = {
            "01": "一月", "02": "二月", "03": "三月", "04": "四月",
            "05": "五月", "06": "六月", "07": "七月", "08": "八月",
            "09": "九月", "10": "十月", "11": "十一月", "12": "十二月",
        }[month_num]
        if month_en in key:
            variants = [span, month_en, month_en.title(), month_cn, month_cn_alt]
            if key.startswith("by") or key.startswith("before") or key.startswith("until"):
                variants.extend([f"到{month_cn_alt}", f"{month_cn_alt}前", f"到{month_cn}", f"{month_cn}前"])
            return variants
    return [span]


def find_enum_markers(text: str, mapping: dict[str, str]) -> list[Match]:
    matches: list[Match] = []
    for surface, value in mapping.items():
        pattern = re.escape(surface)
        flags = re.I if re.search(r"[A-Za-z]", surface) else 0
        for item in re.finditer(pattern, text, flags):
            matches.append(Match(item.group(0), value, item.start(), item.end()))
    return _dedupe_matches(matches)


def find_negations(text: str) -> list[Match]:
    matches: list[Match] = []
    for marker in NEGATION_MARKERS:
        flags = re.I if re.search(r"[A-Za-z]", marker) else 0
        for item in re.finditer(re.escape(marker), text, flags):
            matches.append(Match(item.group(0), "negated", item.start(), item.end()))
    return _dedupe_matches(matches)


def _dedupe_matches(matches: list[Match]) -> list[Match]:
    result: list[Match] = []
    seen: set[tuple[int, int, str]] = set()
    for match in sorted(matches, key=lambda x: (x.start, -(x.end - x.start))):
        key = (match.start, match.end, match.span.casefold())
        if key in seen:
            continue
        if any(match.start >= prev.start and match.end <= prev.end for prev in result):
            continue
        seen.add(key)
        result.append(match)
    return result
