from __future__ import annotations

import json
from pathlib import Path

from .models import SourceConfig


def load_sources(path: Path) -> list[SourceConfig]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources = []
    for raw in payload.get("sources", []):
        sources.append(
            SourceConfig(
                id=raw["id"],
                label=raw["label"],
                type=raw["type"],
                enabled=raw.get("enabled", True),
                list_url=raw.get("list_url"),
                max_items=int(raw.get("max_items", 20)),
                note=raw.get("note"),
            )
        )
    return sources


def load_keywords(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
