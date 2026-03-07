from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SourceConfig:
    id: str
    label: str
    type: str
    enabled: bool
    list_url: str | None
    max_items: int
    note: str | None = None


@dataclass
class MonitoredItem:
    source_id: str
    source_label: str
    url: str
    title: str
    summary: str
    body: str
    published_at: str | None = None
    relevant: bool = False
    confidence: str = "low"
    matched_terms: list[str] = field(default_factory=list)


@dataclass
class Classification:
    relevant: bool
    confidence: str
    matched_terms: list[str] = field(default_factory=list)

