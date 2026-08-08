from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..linking.linker import EntityLinkResult
from ..models import NormalizedItem, parse_iso8601
from ..reporting.digest import iso_utc, report_window


@dataclass(slots=True, frozen=True)
class GrowthMetric:
    current: int
    previous: int
    delta: int
    growth_percent: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class TopicMomentum:
    topic: str
    window_days: int
    current_entities: int
    previous_entities: int
    current_share: float
    previous_share: float
    count_growth_percent: float | None
    momentum_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class RecurringEntity:
    entity_id: str
    title: str
    url: str
    item_count: int
    active_days: int
    sources: tuple[str, ...]
    kinds: tuple[str, ...]
    topics: tuple[str, ...]
    last_seen: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["sources"] = list(self.sources)
        data["kinds"] = list(self.kinds)
        data["topics"] = list(self.topics)
        return data


@dataclass(slots=True)
class TrendSnapshot:
    report_date: date
    window_end: datetime
    daily: list[dict[str, Any]]
    topic_momentum: dict[int, list[TopicMomentum]]
    repository_growth: GrowthMetric
    paper_growth: GrowthMetric
    recurring_entities: list[RecurringEntity]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "report_date": self.report_date.isoformat(),
            "window_end": iso_utc(self.window_end),
            "daily": self.daily,
            "topic_momentum": {
                str(window): [entry.to_dict() for entry in entries]
                for window, entries in sorted(self.topic_momentum.items())
            },
            "growth": {
                "repositories": self.repository_growth.to_dict(),
                "papers": self.paper_growth.to_dict(),
            },
            "recurring_entities": [entity.to_dict() for entity in self.recurring_entities],
        }


class LongTermAnalyzer:
    def __init__(
        self,
        analytics_config: dict[str, Any],
        reporting_config: dict[str, Any],
        taxonomy: dict[str, Any],
    ) -> None:
        self.config = analytics_config
        self.timezone = ZoneInfo(reporting_config["timezone"])
        self.boundary_hour = int(reporting_config["day_boundary_hour"])
        self.topic_ids = tuple(topic["id"] for topic in taxonomy["topics"])

    def build(
        self,
        items: Iterable[NormalizedItem],
        links: EntityLinkResult,
        *,
        report_date: date,
    ) -> TrendSnapshot:
        item_list = list(items)
        _, end = report_window(report_date, self.timezone, self.boundary_hour)
        eligible = [item for item in item_list if timestamp_before(item.discovered_at, end)]
        identity_by_item = build_identity_map(eligible, links)
        activity_items = [item for item in eligible if item.metadata.get("reportable") is not False]

        daily = self._daily_aggregates(activity_items, identity_by_item, report_date)
        topic_momentum = {
            window: self._topic_momentum(activity_items, identity_by_item, end, window)
            for window in self.config["trend_windows_days"]
        }
        growth_window = int(self.config["growth"]["primary_window_days"])
        repository_growth = self._new_entity_growth(
            activity_items,
            identity_by_item,
            end,
            growth_window,
            kind="repository",
        )
        paper_growth = self._new_entity_growth(
            activity_items,
            identity_by_item,
            end,
            growth_window,
            kind="paper",
        )
        recurring = self._recurring_entities(activity_items, identity_by_item, end)
        return TrendSnapshot(
            report_date=report_date,
            window_end=end,
            daily=daily,
            topic_momentum=topic_momentum,
            repository_growth=repository_growth,
            paper_growth=paper_growth,
            recurring_entities=recurring,
        )

    def render_markdown(self, snapshot: TrendSnapshot, topic_labels: dict[str, str]) -> str:
        lines = [f"# Vision Research Trends — {snapshot.report_date.isoformat()}", ""]
        lines.append(
            f"As of {snapshot.window_end.astimezone(self.timezone):%Y-%m-%d %H:%M} {self.timezone.key}"
        )
        lines.append("")

        for window in sorted(snapshot.topic_momentum):
            entries = [
                entry for entry in snapshot.topic_momentum[window] if entry.momentum_score > 0
            ]
            lines.extend([f"## Accelerating Topics — {window} days", ""])
            if not entries:
                lines.extend(["No topic met the minimum activity threshold.", ""])
                continue
            lines.extend(
                [
                    "| Topic | Current | Previous | Growth | Momentum |",
                    "| --- | ---: | ---: | ---: | ---: |",
                ]
            )
            for entry in entries:
                label = topic_labels.get(entry.topic, entry.topic)
                growth = format_growth(
                    entry.count_growth_percent, entry.current_entities, entry.previous_entities
                )
                lines.append(
                    f"| {label} | {entry.current_entities} | {entry.previous_entities} | "
                    f"{growth} | {entry.momentum_score:+.2f} |"
                )
            lines.append("")

        growth_window = int(self.config["growth"]["primary_window_days"])
        lines.extend([f"## New Research Entities — {growth_window} days", ""])
        for label, metric in (
            ("Repositories", snapshot.repository_growth),
            ("Papers", snapshot.paper_growth),
        ):
            growth = format_growth(metric.growth_percent, metric.current, metric.previous)
            lines.append(
                f"- **{label}:** {metric.current} current vs {metric.previous} previous ({growth})"
            )
        lines.append("")

        lines.extend(["## Recurring Entities", ""])
        if snapshot.recurring_entities:
            for entity in snapshot.recurring_entities:
                topics = ", ".join(topic_labels.get(topic, topic) for topic in entity.topics[:5])
                details = f"{entity.active_days} active days · {entity.item_count} records"
                if topics:
                    details += f" · {topics}"
                lines.append(f"- [{entity.title}]({entity.url}) — {details}")
        else:
            lines.append("No entity met the recurring-activity threshold.")
        lines.append("")

        lines.extend(["## Recent Daily Volume", ""])
        lines.extend(
            [
                "| Date | Items | Entities | New repos | New papers |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for bucket in snapshot.daily[-14:]:
            lines.append(
                f"| {bucket['date']} | {bucket['items']} | {bucket['entities']} | "
                f"{bucket['new_repositories']} | {bucket['new_papers']} |"
            )
        lines.append("")
        return "\n".join(lines)

    def _daily_aggregates(
        self,
        items: list[NormalizedItem],
        identity_by_item: dict[str, str],
        report_date: date,
    ) -> list[dict[str, Any]]:
        history_days = int(self.config["history_days"])
        start_date = report_date - timedelta(days=history_days - 1)
        buckets: dict[date, dict[str, Any]] = {}
        for offset in range(history_days):
            bucket_date = start_date + timedelta(days=offset)
            buckets[bucket_date] = {
                "date": bucket_date.isoformat(),
                "items": 0,
                "entities": 0,
                "new_repositories": 0,
                "new_papers": 0,
                "kinds": Counter(),
                "sources": Counter(),
                "_entities": set(),
                "_topic_entities": defaultdict(set),
            }

        first_seen = earliest_kind_identity(items, identity_by_item)
        for item in items:
            timestamp = parse_iso8601(item.discovered_at)
            if timestamp is None:
                continue
            bucket_date = activity_date(timestamp, self.timezone, self.boundary_hour)
            if bucket_date not in buckets:
                continue
            bucket = buckets[bucket_date]
            identity = identity_by_item[item.id]
            bucket["items"] += 1
            bucket["_entities"].add(identity)
            bucket["kinds"][item.kind] += 1
            bucket["sources"][item.source] += 1
            for topic in item.topics:
                bucket["_topic_entities"][topic].add(identity)

        for (kind, _identity), timestamp in first_seen.items():
            if kind not in {"repository", "paper"}:
                continue
            bucket_date = activity_date(timestamp, self.timezone, self.boundary_hour)
            if bucket_date not in buckets:
                continue
            field = "new_repositories" if kind == "repository" else "new_papers"
            buckets[bucket_date][field] += 1

        output: list[dict[str, Any]] = []
        for bucket_date in sorted(buckets):
            bucket = buckets[bucket_date]
            topic_counts = {
                topic: len(identities)
                for topic, identities in sorted(bucket["_topic_entities"].items())
            }
            output.append(
                {
                    "date": bucket["date"],
                    "items": bucket["items"],
                    "entities": len(bucket["_entities"]),
                    "new_repositories": bucket["new_repositories"],
                    "new_papers": bucket["new_papers"],
                    "topics": topic_counts,
                    "kinds": dict(sorted(bucket["kinds"].items())),
                    "sources": dict(sorted(bucket["sources"].items())),
                }
            )
        return output

    def _topic_momentum(
        self,
        items: list[NormalizedItem],
        identity_by_item: dict[str, str],
        end: datetime,
        window_days: int,
    ) -> list[TopicMomentum]:
        window = timedelta(days=window_days)
        current = entities_with_topics(items, identity_by_item, end - window, end)
        previous = entities_with_topics(items, identity_by_item, end - 2 * window, end - window)
        current_total = len(current)
        previous_total = len(previous)
        smoothing = float(self.config["momentum"]["smoothing"])
        topic_count = max(1, len(self.topic_ids))
        minimum_current = int(self.config["momentum"]["minimum_current_entities"])

        entries: list[TopicMomentum] = []
        for topic in self.topic_ids:
            current_count = sum(topic in topics for topics in current.values())
            if current_count < minimum_current:
                continue
            previous_count = sum(topic in topics for topics in previous.values())
            current_share = (current_count + smoothing) / (current_total + smoothing * topic_count)
            previous_share = (previous_count + smoothing) / (
                previous_total + smoothing * topic_count
            )
            entries.append(
                TopicMomentum(
                    topic=topic,
                    window_days=window_days,
                    current_entities=current_count,
                    previous_entities=previous_count,
                    current_share=round(current_share, 6),
                    previous_share=round(previous_share, 6),
                    count_growth_percent=growth_percent(current_count, previous_count),
                    momentum_score=round(math.log2(current_share / previous_share), 4),
                )
            )
        entries.sort(
            key=lambda entry: (-entry.momentum_score, -entry.current_entities, entry.topic)
        )
        limit = int(self.config["momentum"]["top_topics_per_window"])
        return entries[:limit]

    def _new_entity_growth(
        self,
        items: list[NormalizedItem],
        identity_by_item: dict[str, str],
        end: datetime,
        window_days: int,
        *,
        kind: str,
    ) -> GrowthMetric:
        first_seen = earliest_kind_identity(items, identity_by_item)
        window = timedelta(days=window_days)
        current_start = end - window
        previous_start = end - 2 * window
        current = sum(
            current_start <= timestamp < end
            for (item_kind, _), timestamp in first_seen.items()
            if item_kind == kind
        )
        previous = sum(
            previous_start <= timestamp < current_start
            for (item_kind, _), timestamp in first_seen.items()
            if item_kind == kind
        )
        return GrowthMetric(
            current, previous, current - previous, growth_percent(current, previous)
        )

    def _recurring_entities(
        self,
        items: list[NormalizedItem],
        identity_by_item: dict[str, str],
        end: datetime,
    ) -> list[RecurringEntity]:
        config = self.config["recurring_entities"]
        start = end - timedelta(days=int(config["lookback_days"]))
        grouped: dict[str, list[NormalizedItem]] = defaultdict(list)
        for item in items:
            timestamp = parse_iso8601(item.discovered_at)
            if timestamp is None or not (start <= timestamp < end):
                continue
            grouped[identity_by_item[item.id]].append(item)

        recurring: list[RecurringEntity] = []
        for entity_id, group in grouped.items():
            active_dates = {
                activity_date(timestamp, self.timezone, self.boundary_hour)
                for item in group
                if (timestamp := parse_iso8601(item.discovered_at)) is not None
            }
            if len(group) < int(config["minimum_activity_items"]):
                continue
            if len(active_dates) < int(config["minimum_active_days"]):
                continue
            representative = choose_representative(group)
            last_seen = max(item.discovered_at for item in group)
            recurring.append(
                RecurringEntity(
                    entity_id=entity_id,
                    title=representative.title,
                    url=representative.url,
                    item_count=len(group),
                    active_days=len(active_dates),
                    sources=tuple(sorted({item.source for item in group})),
                    kinds=tuple(sorted({item.kind for item in group})),
                    topics=tuple(sorted({topic for item in group for topic in item.topics})),
                    last_seen=last_seen,
                )
            )
        recurring.sort(
            key=lambda entity: (-entity.active_days, -entity.item_count, entity.entity_id)
        )
        return recurring[: int(config["limit"])]


def build_identity_map(items: Iterable[NormalizedItem], links: EntityLinkResult) -> dict[str, str]:
    identity_by_item: dict[str, str] = {}
    for entity_id, item_ids in links.entities.items():
        for item_id in item_ids:
            identity_by_item[item_id] = entity_id
    for item in items:
        identity_by_item.setdefault(item.id, item.id)
    return identity_by_item


def earliest_kind_identity(
    items: Iterable[NormalizedItem],
    identity_by_item: dict[str, str],
) -> dict[tuple[str, str], datetime]:
    earliest: dict[tuple[str, str], datetime] = {}
    for item in items:
        if item.kind not in {"repository", "paper"}:
            continue
        timestamp = parse_iso8601(item.discovered_at)
        if timestamp is None:
            continue
        key = (item.kind, identity_by_item[item.id])
        current = earliest.get(key)
        if current is None or timestamp < current:
            earliest[key] = timestamp
    return earliest


def entities_with_topics(
    items: Iterable[NormalizedItem],
    identity_by_item: dict[str, str],
    start: datetime,
    end: datetime,
) -> dict[str, set[str]]:
    entities: dict[str, set[str]] = defaultdict(set)
    for item in items:
        timestamp = parse_iso8601(item.discovered_at)
        if timestamp is None or not (start <= timestamp < end):
            continue
        identity = identity_by_item[item.id]
        entities[identity].update(item.topics)
    return dict(entities)


def activity_date(timestamp: datetime, timezone_info: ZoneInfo, boundary_hour: int) -> date:
    shifted = timestamp.astimezone(timezone_info) - timedelta(hours=boundary_hour)
    return shifted.date() + timedelta(days=1)


def timestamp_before(value: str, end: datetime) -> bool:
    timestamp = parse_iso8601(value)
    return timestamp is not None and timestamp < end


def growth_percent(current: int, previous: int) -> float | None:
    if previous == 0:
        return 0.0 if current == 0 else None
    return round((current - previous) / previous * 100.0, 2)


def format_growth(value: float | None, current: int, previous: int) -> str:
    if value is None:
        return "new" if current > previous else "n/a"
    return f"{value:+.1f}%"


def choose_representative(items: Iterable[NormalizedItem]) -> NormalizedItem:
    priority = {
        "repository": 0,
        "paper": 1,
        "model": 2,
        "project": 3,
        "article": 4,
        "release": 5,
        "tag": 6,
        "commit": 7,
        "event": 8,
    }
    return min(items, key=lambda item: (priority.get(item.kind, 99), item.id))
