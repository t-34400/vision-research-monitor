from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from ..models import NormalizedItem, parse_iso8601


@dataclass(slots=True, frozen=True)
class RankingSignals:
    priority: float
    relevance: float
    freshness: float
    novelty: float
    popularity: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class RankedItem:
    item: NormalizedItem
    signals: RankingSignals
    total: float
    watched_override: bool
    change_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item.id,
            "signals": self.signals.to_dict(),
            "total": self.total,
            "watched_override": self.watched_override,
            "change_label": self.change_label,
        }


class ResearchRanker:
    def __init__(self, config: dict[str, Any], venue_priorities: dict[str, str]) -> None:
        self.config = config["ranking"]
        self.venue_priorities = venue_priorities

    def rank(self, item: NormalizedItem, *, reference_time: datetime) -> RankedItem:
        signals = RankingSignals(
            priority=self._priority(item),
            relevance=self._relevance(item),
            freshness=self._freshness(item, reference_time),
            novelty=self._novelty(item),
            popularity=self._popularity(item),
        )
        weights = self.config["weights"]
        weight_sum = sum(float(value) for value in weights.values())
        weighted = sum(float(weights[name]) * getattr(signals, name) for name in weights)
        total = round(weighted / weight_sum, 4)
        source_priority = item.priority.get("source")
        watched_override = isinstance(source_priority, (int, float)) and float(source_priority) >= 1.0
        return RankedItem(item, signals, total, watched_override, change_label(item))

    def included(self, ranked: RankedItem) -> bool:
        if ranked.item.metadata.get("reportable") is False:
            return False
        return ranked.watched_override or ranked.total >= float(self.config["minimum_total_score"])

    def _priority(self, item: NormalizedItem) -> float:
        explicit = item.priority.get("source")
        explicit_value = float(explicit) if isinstance(explicit, (int, float)) else 0.0
        source_default = float(self.config["source_priority_defaults"].get(item.source, 0.0))
        venue_level = self.venue_priorities.get(item.venue or "")
        venue_value = float(self.config["venue_priority"].get(venue_level, 0.0)) if venue_level else 0.0
        return clamp(max(explicit_value, source_default, venue_value))

    def _relevance(self, item: NormalizedItem) -> float:
        relevance = item.scores.get("relevance")
        if isinstance(relevance, (int, float)):
            return clamp(float(relevance))
        return float(self.config["relevance_fallback_with_topics"]) if item.topics else 0.0

    def _freshness(self, item: NormalizedItem, reference_time: datetime) -> float:
        timestamp = effective_event_time(item)
        if timestamp is None:
            return 0.0
        age_hours = max(0.0, (reference_time - timestamp).total_seconds() / 3600.0)
        half_life = float(self.config["freshness_half_life_hours"])
        return round(0.5 ** (age_hours / half_life), 4)

    def _novelty(self, item: NormalizedItem) -> float:
        novelty = self.config["novelty"]
        action = item.metadata.get("action")
        actions = novelty.get("actions", {})
        if isinstance(action, str) and action in actions:
            return clamp(float(actions[action]))
        value = novelty.get(item.kind, 0.0)
        return clamp(float(value)) if isinstance(value, (int, float)) else 0.0

    def _popularity(self, item: NormalizedItem) -> float:
        delta = item.metadata.get("stars_delta")
        if not isinstance(delta, (int, float)) or delta <= 0:
            return 0.0
        reference = float(self.config["popularity_reference_delta"])
        return round(clamp(math.log1p(float(delta)) / math.log1p(reference)), 4)


def effective_event_time(item: NormalizedItem) -> datetime | None:
    action = item.metadata.get("action")
    if action == "updated":
        return parse_iso8601(item.updated_at) or parse_iso8601(item.discovered_at)
    if item.kind == "paper":
        return parse_iso8601(item.published_at) or parse_iso8601(item.discovered_at)
    if item.kind == "repository":
        return (
            parse_iso8601(item.updated_at)
            or parse_iso8601(item.published_at)
            or parse_iso8601(item.discovered_at)
        )
    return (
        parse_iso8601(item.published_at)
        or parse_iso8601(item.updated_at)
        or parse_iso8601(item.discovered_at)
    )


def change_label(item: NormalizedItem) -> str:
    action = item.metadata.get("action")
    status = item.metadata.get("status")
    if action == "status_changed" and status == "accepted":
        return "ACCEPTED"
    if item.kind == "paper" and status == "accepted" and item.source == "openreview":
        return "ACCEPTED"
    if item.kind == "release" or action == "released":
        return "RELEASED"
    if item.kind in {"repository", "paper"} or action in {"created", "discovered", "published"}:
        return "NEW"
    return "UPDATED"


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
