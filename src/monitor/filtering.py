from __future__ import annotations

from .models import Classification, MonitoredItem


def _find_hits(text: str, terms: list[str]) -> list[str]:
    lowered = text.lower()
    hits = []
    for term in terms:
        if term.lower() in lowered and term not in hits:
            hits.append(term)
    return hits


def classify_item(item: MonitoredItem, keywords: dict) -> Classification:
    high_terms = keywords.get("high_confidence_terms", [])
    medium_terms = keywords.get("medium_confidence_terms", [])
    min_medium_hits_for_high = int(keywords.get("min_medium_hits_for_high", 2))

    title = item.title or ""
    other_text = " ".join(part for part in [item.summary, item.body[:4000]] if part)

    title_high = _find_hits(title, high_terms)
    other_high = _find_hits(other_text, high_terms)
    title_medium = _find_hits(title, medium_terms)
    other_medium = _find_hits(other_text, medium_terms)

    matched_terms = []
    for group in [title_high, other_high, title_medium, other_medium]:
        for term in group:
            if term not in matched_terms:
                matched_terms.append(term)

    if title_high or other_high:
        return Classification(relevant=True, confidence="high", matched_terms=matched_terms)

    medium_hit_count = len({*title_medium, *other_medium})
    if medium_hit_count >= min_medium_hits_for_high:
        return Classification(relevant=True, confidence="high", matched_terms=matched_terms)

    if matched_terms:
        return Classification(relevant=True, confidence="medium", matched_terms=matched_terms)

    return Classification(relevant=False, confidence="low", matched_terms=[])

