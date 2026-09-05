from __future__ import annotations

import re

from .models import Classification, MonitoredItem


def _term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    prefix = r"(?<![A-Za-z0-9])" if term[:1].isalnum() else ""
    suffix = r"(?![A-Za-z0-9])" if term[-1:].isalnum() else ""
    return re.compile(f"{prefix}{escaped}{suffix}", re.IGNORECASE)


def _find_hits(text: str, terms: list[str]) -> list[str]:
    hits = []
    for term in terms:
        if _term_pattern(term).search(text) and term not in hits:
            hits.append(term)
    return hits


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(term).strip() for term in value if str(term).strip()]


def _matches_excluded_context(text: str, rule: object) -> bool:
    if not isinstance(rule, dict):
        return False

    terms = _string_list(rule.get("terms"))
    context_terms = _string_list(rule.get("context_terms"))
    unless_terms = _string_list(rule.get("unless_terms"))

    if unless_terms and _find_hits(text, unless_terms):
        return False
    return bool(_find_hits(text, terms) and _find_hits(text, context_terms))


def _is_excluded_context(text: str, keywords: dict) -> bool:
    rules = keywords.get("excluded_contexts", [])
    if not isinstance(rules, list):
        return False
    return any(_matches_excluded_context(text, rule) for rule in rules)


def _matches_excluded_attribution(text: str, rule: object) -> bool:
    if not isinstance(rule, dict):
        return False

    outlet_terms = _string_list(rule.get("outlet_terms"))
    attribution_terms = _string_list(rule.get("attribution_terms"))
    sentence_segments = re.sub(r"[.!?。！？]+", "\n", text).splitlines()
    return any(
        _find_hits(segment, outlet_terms) and _find_hits(segment, attribution_terms)
        for segment in sentence_segments
    )


def _is_excluded_attribution(text: str, keywords: dict) -> bool:
    rules = keywords.get("excluded_attribution_rules", [])
    if not isinstance(rules, list):
        return False
    return any(_matches_excluded_attribution(text, rule) for rule in rules)


def classify_item(item: MonitoredItem, keywords: dict) -> Classification:
    high_terms = keywords.get("high_confidence_terms", [])
    company_terms = keywords.get("korean_company_terms", [])
    medium_terms = keywords.get("medium_confidence_terms", [])
    min_medium_hits_for_high = int(keywords.get("min_medium_hits_for_high", 2))

    title = item.title or ""
    other_text = " ".join(part for part in [item.summary, item.body[:4000]] if part)
    combined_text = "\n".join(part for part in [title, other_text] if part)

    title_high = _find_hits(title, high_terms)
    other_high = _find_hits(other_text, high_terms)
    title_company = _find_hits(title, company_terms)
    other_company = _find_hits(other_text, company_terms)
    title_medium = _find_hits(title, medium_terms)
    other_medium = _find_hits(other_text, medium_terms)

    matched_terms = []
    for group in [title_high, other_high, title_company, other_company, title_medium, other_medium]:
        for term in group:
            if term not in matched_terms:
                matched_terms.append(term)

    if _is_excluded_attribution(combined_text, keywords):
        return Classification(
            relevant=False,
            confidence="low",
            matched_terms=[],
            excluded=True,
        )

    if (
        matched_terms
        and not (title_high or other_high or title_company or other_company)
        and _is_excluded_context(combined_text, keywords)
    ):
        return Classification(
            relevant=False,
            confidence="low",
            matched_terms=[],
            excluded=True,
        )

    if title_high or other_high or title_company or other_company:
        return Classification(relevant=True, confidence="high", matched_terms=matched_terms)

    medium_hit_count = len({*title_medium, *other_medium})
    if medium_hit_count >= min_medium_hits_for_high:
        return Classification(relevant=True, confidence="high", matched_terms=matched_terms)

    if matched_terms:
        return Classification(relevant=True, confidence="medium", matched_terms=matched_terms)

    return Classification(relevant=False, confidence="low", matched_terms=[])
