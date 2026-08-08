from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable

from ..linking.linker import EntityLinkResult
from ..models import NormalizedItem, parse_iso8601
from .trends import build_identity_map


@dataclass(slots=True, frozen=True)
class ArchiveRecord:
    id: str
    entity_id: str
    title: str
    url: str
    source: str
    kind: str
    discovered_at: str
    published_at: str | None
    updated_at: str | None
    summary: str | None
    authors: tuple[str, ...]
    organization: str | None
    venue: str | None
    topics: tuple[str, ...]
    reportable: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["authors"] = list(self.authors)
        data["topics"] = list(self.topics)
        return data


@dataclass(slots=True)
class ArchiveIndex:
    generated_for_date: str
    cutoff: str
    records: list[ArchiveRecord]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "generated_for_date": self.generated_for_date,
            "cutoff": self.cutoff,
            "records": [record.to_dict() for record in self.records],
        }


def build_archive_index(
    items: Iterable[NormalizedItem],
    links: EntityLinkResult,
    *,
    generated_for_date: str,
    cutoff: datetime,
    maximum_summary_characters: int,
) -> ArchiveIndex:
    item_list = list(items)
    identity_by_item = build_identity_map(item_list, links)
    records: list[ArchiveRecord] = []
    for item in item_list:
        discovered = parse_iso8601(item.discovered_at)
        if discovered is None or discovered >= cutoff:
            continue
        records.append(
            ArchiveRecord(
                id=item.id,
                entity_id=identity_by_item[item.id],
                title=item.title,
                url=item.url,
                source=item.source,
                kind=item.kind,
                discovered_at=item.discovered_at,
                published_at=item.published_at,
                updated_at=item.updated_at,
                summary=compact(item.summary, maximum_summary_characters),
                authors=tuple(item.authors),
                organization=item.organization,
                venue=item.venue,
                topics=tuple(item.topics),
                reportable=item.metadata.get("reportable") is not False,
            )
        )
    records.sort(key=lambda record: (record.discovered_at, record.id), reverse=True)
    return ArchiveIndex(generated_for_date, cutoff.isoformat().replace("+00:00", "Z"), records)


def search_archive(
    index: ArchiveIndex,
    *,
    query: str = "",
    topics: set[str] | None = None,
    sources: set[str] | None = None,
    kinds: set[str] | None = None,
    since: datetime | None = None,
    include_hidden: bool = False,
    limit: int = 20,
) -> list[ArchiveRecord]:
    query_tokens = [token for token in query.casefold().split() if token]
    matches: list[tuple[int, ArchiveRecord]] = []
    for record in index.records:
        if not include_hidden and not record.reportable:
            continue
        if topics and not topics.issubset(set(record.topics)):
            continue
        if sources and record.source not in sources:
            continue
        if kinds and record.kind not in kinds:
            continue
        discovered = parse_iso8601(record.discovered_at)
        if since is not None and (discovered is None or discovered < since):
            continue
        score = archive_match_score(record, query_tokens)
        if query_tokens and score <= 0:
            continue
        matches.append((score, record))
    if query_tokens:
        matches.sort(key=lambda pair: (-pair[0], -datetime_rank(pair[1].discovered_at), pair[1].id))
    else:
        matches.sort(key=lambda pair: (-datetime_rank(pair[1].discovered_at), pair[1].id))
    return [record for _, record in matches[:limit]]


def archive_match_score(record: ArchiveRecord, query_tokens: list[str]) -> int:
    if not query_tokens:
        return 1
    title = record.title.casefold()
    summary = (record.summary or "").casefold()
    metadata = " ".join(
        [
            " ".join(record.authors),
            record.organization or "",
            record.venue or "",
            " ".join(record.topics),
            record.source,
            record.kind,
        ]
    ).casefold()
    score = 0
    for token in query_tokens:
        token_score = 0
        if token in title:
            token_score = max(token_score, 10)
        if token in summary:
            token_score = max(token_score, 3)
        if token in metadata:
            token_score = max(token_score, 5)
        if token_score == 0:
            return 0
        score += token_score
    phrase = " ".join(query_tokens)
    if phrase and phrase in title:
        score += 30
    return score


def archive_index_from_dict(data: dict[str, Any]) -> ArchiveIndex:
    if data.get("version") != 1:
        raise ValueError("Unsupported archive index version")
    records = []
    for raw in data.get("records", []):
        records.append(
            ArchiveRecord(
                id=raw["id"],
                entity_id=raw["entity_id"],
                title=raw["title"],
                url=raw["url"],
                source=raw["source"],
                kind=raw["kind"],
                discovered_at=raw["discovered_at"],
                published_at=raw.get("published_at"),
                updated_at=raw.get("updated_at"),
                summary=raw.get("summary"),
                authors=tuple(raw.get("authors", [])),
                organization=raw.get("organization"),
                venue=raw.get("venue"),
                topics=tuple(raw.get("topics", [])),
                reportable=bool(raw.get("reportable", True)),
            )
        )
    return ArchiveIndex(data["generated_for_date"], data["cutoff"], records)


def compact(value: str | None, limit: int) -> str | None:
    if value is None or limit <= 0:
        return None
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    if limit == 1:
        return "…"
    return normalized[: limit - 1].rstrip() + "…"


def datetime_rank(value: str) -> float:
    timestamp = parse_iso8601(value)
    return timestamp.timestamp() if timestamp is not None else 0.0
