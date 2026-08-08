from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..linking.linker import EntityLinkResult
from ..models import NormalizedItem, parse_iso8601
from .ranking import RankedItem, ResearchRanker


@dataclass(slots=True)
class DigestResult:
    report_date: date
    window_start: datetime
    window_end: datetime
    ranked: list[RankedItem]
    markdown: str

    def ranking_document(self) -> dict[str, Any]:
        return {
            "version": 1,
            "report_date": self.report_date.isoformat(),
            "window_start": iso_utc(self.window_start),
            "window_end": iso_utc(self.window_end),
            "items": [ranked.to_dict() for ranked in self.ranked],
        }


class DailyDigestBuilder:
    def __init__(
        self,
        config: dict[str, Any],
        taxonomy: dict[str, Any],
        venues: dict[str, Any],
    ) -> None:
        self.config = config
        self.timezone = ZoneInfo(config["timezone"])
        self.topic_labels = {topic["id"]: topic["label"] for topic in taxonomy["topics"]}
        self.venue_labels = {venue["id"]: venue["name"] for venue in venues["venues"]}
        venue_priorities = {venue["id"]: venue["priority"] for venue in venues["venues"]}
        self.ranker = ResearchRanker(config, venue_priorities)

    def build(
        self,
        items: Iterable[NormalizedItem],
        links: EntityLinkResult,
        *,
        report_date: date,
    ) -> DigestResult:
        start, end = report_window(
            report_date, self.timezone, int(self.config["day_boundary_hour"])
        )
        selected = [item for item in items if is_in_window(item.discovered_at, start, end)]
        ranked = [self.ranker.rank(item, reference_time=end) for item in selected]
        ranked = [item for item in ranked if self.ranker.included(item)]
        ranked.sort(key=ranked_sort_key)
        deduped = self._dedupe_papers(ranked, links)
        markdown = self._render(report_date, start, end, deduped, links)
        return DigestResult(report_date, start, end, deduped, markdown)

    def _dedupe_papers(self, ranked: list[RankedItem], links: EntityLinkResult) -> list[RankedItem]:
        entity_by_item: dict[str, str] = {}
        for entity_id, item_ids in links.entities.items():
            for item_id in item_ids:
                entity_by_item[item_id] = entity_id

        best: dict[str, RankedItem] = {}
        passthrough: list[RankedItem] = []
        for candidate in ranked:
            if candidate.item.kind != "paper":
                passthrough.append(candidate)
                continue
            entity_id = entity_by_item.get(candidate.item.id)
            if entity_id is None:
                passthrough.append(candidate)
                continue
            current = best.get(entity_id)
            if current is None or ranked_sort_key(candidate) < ranked_sort_key(current):
                best[entity_id] = candidate
        combined = passthrough + list(best.values())
        combined.sort(key=ranked_sort_key)
        return combined

    def _render(
        self,
        report_date: date,
        start: datetime,
        end: datetime,
        ranked: list[RankedItem],
        links: EntityLinkResult,
    ) -> str:
        title = self.config["report"]["title"]
        lines = [f"# {title} — {report_date.isoformat()}", ""]
        lines.append(
            f"Window: {start.astimezone(self.timezone):%Y-%m-%d %H:%M} – "
            f"{end.astimezone(self.timezone):%Y-%m-%d %H:%M} {self.config['timezone']}"
        )
        lines.append("")
        if not ranked:
            lines.extend(["No items met the reporting threshold for this window.", ""])
            return "\n".join(lines)

        sections = self._sections(ranked)
        rendered_ids: set[str] = set()
        for heading, key in (
            ("Priority Watch", "priority_watch"),
            ("Accepted Papers", "accepted_papers"),
            ("New Papers", "new_papers"),
            ("New Repositories", "new_repositories"),
            ("Models & Demos", "models_and_demos"),
            ("Research Announcements", "research_announcements"),
            ("Project Updates", "project_updates"),
            ("Other", "other"),
        ):
            entries = sections[key]
            if not entries:
                continue
            lines.extend([f"## {heading}", ""])
            limit = (
                None
                if key == "priority_watch"
                else int(self.config["report"]["section_limits"].get(key, 0))
            )
            visible = entries if not limit else entries[:limit]
            for ranked_item in visible:
                rendered_ids.add(ranked_item.item.id)
                lines.extend(self._render_item(ranked_item, links))
            hidden = len(entries) - len(visible)
            if hidden > 0:
                lines.extend([f"_+{hidden} more items omitted by section limit._", ""])

        return "\n".join(lines).rstrip() + "\n"

    def _sections(self, ranked: list[RankedItem]) -> dict[str, list[RankedItem]]:
        sections = {
            "priority_watch": [],
            "accepted_papers": [],
            "new_papers": [],
            "new_repositories": [],
            "models_and_demos": [],
            "research_announcements": [],
            "project_updates": [],
            "other": [],
        }
        for candidate in ranked:
            item = candidate.item
            if candidate.watched_override:
                sections["priority_watch"].append(candidate)
            elif candidate.change_label == "ACCEPTED":
                sections["accepted_papers"].append(candidate)
            elif item.kind == "paper":
                sections["new_papers"].append(candidate)
            elif item.kind == "repository":
                sections["new_repositories"].append(candidate)
            elif item.kind in {"model", "project"}:
                sections["models_and_demos"].append(candidate)
            elif item.kind == "article":
                sections["research_announcements"].append(candidate)
            elif item.kind in {"release", "tag", "commit", "event"}:
                sections["project_updates"].append(candidate)
            else:
                sections["other"].append(candidate)
        return sections

    def _render_item(self, ranked: RankedItem, links: EntityLinkResult) -> list[str]:
        item = ranked.item
        lines = [f"- **[{ranked.change_label}] [{escape_markdown(item.title)}]({item.url})**"]
        details: list[str] = [item.source]
        if item.venue:
            year = item.metadata.get("venue_year")
            venue = item.venue.upper() if len(item.venue) <= 6 else item.venue
            details.append(f"{venue} {year}" if year else venue)
        if item.topics:
            details.append(
                ", ".join(self.topic_labels.get(topic, topic) for topic in item.topics[:5])
            )
        if self.config["report"]["include_score"]:
            details.append(f"score {ranked.total:.2f}")
        lines.append(f"  - {' · '.join(details)}")

        summary = compact_summary(
            item.summary, int(self.config["report"]["summary_max_characters"])
        )
        if summary:
            lines.append(f"  - {summary}")

        resource_links = []
        project_urls = item.metadata.get("project_urls")
        code_urls = item.metadata.get("code_urls")
        if isinstance(project_urls, list) and project_urls:
            resource_links.append(f"[Project]({project_urls[0]})")
        if isinstance(code_urls, list) and code_urls:
            resource_links.append(f"[Code]({code_urls[0]})")
        if resource_links:
            lines.append(f"  - {' · '.join(resource_links)}")

        related = links.related_items.get(item.id, [])
        if related:
            lines.append(f"  - Related records: {', '.join(f'`{value}`' for value in related[:6])}")
        lines.append("")
        return lines


def report_window(
    report_date: date, timezone_info: ZoneInfo, boundary_hour: int
) -> tuple[datetime, datetime]:
    local_end = datetime.combine(report_date, time(boundary_hour), tzinfo=timezone_info)
    local_start = local_end - timedelta(days=1)
    return local_start.astimezone(UTC), local_end.astimezone(UTC)


def is_in_window(value: str, start: datetime, end: datetime) -> bool:
    timestamp = parse_iso8601(value)
    return timestamp is not None and start <= timestamp < end


def ranked_sort_key(candidate: RankedItem) -> tuple[float, float, str]:
    return (-candidate.total, -candidate.signals.freshness, candidate.item.id)


def compact_summary(value: str | None, limit: int) -> str | None:
    if not value or limit <= 0:
        return None
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    if limit <= 1:
        return "…"
    return compact[: limit - 1].rstrip() + "…"


def escape_markdown(value: str) -> str:
    return value.replace("[", "\\[").replace("]", "\\]")


def iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
