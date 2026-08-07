from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso8601(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso8601(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


@dataclass(slots=True)
class NormalizedItem:
    id: str
    source: str
    source_id: str
    kind: str
    title: str
    url: str
    discovered_at: str
    published_at: str | None = None
    updated_at: str | None = None
    summary: str | None = None
    authors: list[str] = field(default_factory=list)
    organization: str | None = None
    venue: str | None = None
    topics: list[str] = field(default_factory=list)
    matched_terms: list[str] = field(default_factory=list)
    priority: dict[str, float | None] = field(default_factory=dict)
    scores: dict[str, float | None] = field(default_factory=dict)
    related_items: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
