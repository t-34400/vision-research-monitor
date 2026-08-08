from __future__ import annotations

import email.utils
import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any

from ..academic.matching import AcademicLexicalMatcher
from ..classification.semantic import (
    ClassificationResult,
    SemanticClassificationPipeline,
    rejected_lexical,
)
from ..http import HttpClient
from ..linking.normalize import extract_urls
from ..models import NormalizedItem, to_iso8601
from .common import SourceRunResult, collection_window, initialize_result, normalize_window


@dataclass(slots=True, frozen=True)
class FeedEntry:
    identity: str
    title: str
    url: str
    summary: str
    published_at: datetime | None
    updated_at: datetime | None
    authors: list[str]
    categories: list[str]


class ResearchFeedCollector:
    def __init__(
        self,
        client: HttpClient,
        state: dict[str, Any],
        config: dict[str, Any],
        taxonomy: dict[str, Any],
        classifier: SemanticClassificationPipeline | None = None,
    ) -> None:
        self.client = client
        self.state = state
        self.config = config
        self.matcher = AcademicLexicalMatcher(taxonomy, config["matching"])
        self.classifier = classifier

    def collection_window(self, run_at: datetime) -> tuple[datetime, datetime]:
        source_state = self.state.setdefault("sources", {}).setdefault("research_blogs", {})
        return collection_window(
            run_at,
            source_state.get("last_successful_at"),
            self.config["window"],
            source_name="Research blogs",
        )

    def collect(
        self,
        run_at: datetime,
        *,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> SourceRunResult:
        run_at = run_at.astimezone(UTC)
        if window_start is None or window_end is None:
            window_start, window_end = self.collection_window(run_at)
        window_start, window_end = normalize_window(window_start, window_end)
        result = initialize_result(window_start, window_end)
        threshold = float(self.config["matching"]["minimum_relevance_score"])

        for feed in self.config["research_blogs"]["feeds"]:
            if not feed.get("enabled", True):
                continue
            try:
                response = self.client.get_text(
                    feed["url"],
                    accept="application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9",
                )
                entries = parse_feed(response.data)
                for entry in entries:
                    event_time = entry.published_at or entry.updated_at
                    if event_time is None or not window_start <= event_time <= window_end:
                        continue
                    match = self.matcher.match(
                        entry.title, entry.summary, keywords=entry.categories
                    )
                    classification = self._classify(entry.title, entry.summary, match, threshold)
                    if not classification.accepted:
                        continue
                    result.items.append(normalize_feed_entry(feed, entry, classification, run_at))
            except Exception as exc:
                result.add_error(f"research_blog:{feed['id']}", exc)

        result.items.sort(key=lambda item: (item.published_at or "", item.source_id))
        return result

    def _classify(
        self, title: str, text: str, match: Any, threshold: float
    ) -> ClassificationResult:
        if self.classifier is None:
            if match.score < threshold:
                return rejected_lexical(match.score, match.topics, match.matched_terms)
            return ClassificationResult(
                accepted=True,
                relevance=match.score,
                topics=match.topics,
                matched_terms=match.matched_terms,
                evidence={
                    "method": "lexical",
                    "lexical_score": match.score,
                    "semantic_model": None,
                    "llm_model": None,
                },
            )
        return self.classifier.classify(
            title=title,
            text=text,
            lexical_score=match.score,
            lexical_topics=match.topics,
            matched_terms=match.matched_terms,
            lexical_threshold=threshold,
        )


def normalize_feed_entry(
    feed: dict[str, Any],
    entry: FeedEntry,
    classification: ClassificationResult,
    run_at: datetime,
) -> NormalizedItem:
    digest = hashlib.sha256(f"{feed['id']}\n{entry.identity}".encode()).hexdigest()[:24]
    return NormalizedItem(
        id=f"research_blog:article:{digest}",
        source="research_blog",
        source_id=f"{feed['id']}:{digest}",
        kind="article",
        title=entry.title,
        url=entry.url,
        discovered_at=to_iso8601(run_at),
        published_at=to_iso8601(entry.published_at) if entry.published_at else None,
        updated_at=to_iso8601(entry.updated_at) if entry.updated_at else None,
        summary=entry.summary or None,
        authors=entry.authors,
        organization=feed["organization"],
        topics=classification.topics,
        matched_terms=classification.matched_terms,
        priority={"source": float(feed["priority"])},
        scores={"relevance": classification.relevance},
        metadata={
            "action": "published",
            "feed_id": feed["id"],
            "feed_name": feed["name"],
            "categories": entry.categories,
            "links": sorted(set(extract_urls(entry.summary))),
            "classification": classification.evidence,
        },
    )


def parse_feed(xml: str) -> list[FeedEntry]:
    root = ET.fromstring(xml)
    root_name = local_name(root.tag)
    if root_name == "rss" or root.find("channel") is not None:
        return parse_rss(root)
    if root_name == "feed":
        return parse_atom(root)
    raise ValueError(f"Unsupported feed root element: {root.tag}")


def parse_rss(root: ET.Element) -> list[FeedEntry]:
    channel = root.find("channel")
    if channel is None:
        return []
    entries: list[FeedEntry] = []
    for item in channel.findall("item"):
        title = child_text(item, "title")
        link = child_text(item, "link")
        guid = child_text(item, "guid") or link
        description = child_text(item, "description")
        content = first_child_text_by_local(item, "encoded")
        summary = html_to_text(content or description)
        published = parse_feed_datetime(
            child_text(item, "pubDate") or first_child_text_by_local(item, "date")
        )
        categories = [
            clean_text(node.text or "")
            for node in item.findall("category")
            if clean_text(node.text or "")
        ]
        author = first_child_text_by_local(item, "creator") or child_text(item, "author")
        if title and link and guid:
            entries.append(
                FeedEntry(
                    identity=guid,
                    title=clean_text(title),
                    url=link.strip(),
                    summary=summary,
                    published_at=published,
                    updated_at=None,
                    authors=[clean_text(author)] if author else [],
                    categories=categories,
                )
            )
    return entries


def parse_atom(root: ET.Element) -> list[FeedEntry]:
    entries: list[FeedEntry] = []
    for entry in [node for node in root if local_name(node.tag) == "entry"]:
        title = first_child_text_by_local(entry, "title")
        identity = first_child_text_by_local(entry, "id")
        link = ""
        for node in entry:
            if local_name(node.tag) != "link":
                continue
            rel = node.attrib.get("rel", "alternate")
            if rel == "alternate" and node.attrib.get("href"):
                link = node.attrib["href"]
                break
        summary_html = first_child_text_by_local(entry, "content") or first_child_text_by_local(
            entry, "summary"
        )
        published = parse_feed_datetime(first_child_text_by_local(entry, "published"))
        updated = parse_feed_datetime(first_child_text_by_local(entry, "updated"))
        authors = []
        for author_node in [node for node in entry if local_name(node.tag) == "author"]:
            name = first_child_text_by_local(author_node, "name")
            if name:
                authors.append(clean_text(name))
        categories = [
            node.attrib.get("term", "").strip()
            for node in entry
            if local_name(node.tag) == "category" and node.attrib.get("term", "").strip()
        ]
        if title and link and identity:
            entries.append(
                FeedEntry(
                    identity=identity,
                    title=clean_text(title),
                    url=link,
                    summary=html_to_text(summary_html),
                    published_at=published,
                    updated_at=updated,
                    authors=authors,
                    categories=categories,
                )
            )
    return entries


def parse_feed_datetime(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    raw = value.strip()
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    parser = _TextExtractor()
    parser.feed(value)
    return join_text_fragments(parser.parts)


def child_text(node: ET.Element, name: str) -> str | None:
    child = node.find(name)
    return child.text if child is not None else None


def first_child_text_by_local(node: ET.Element, name: str) -> str | None:
    for child in node:
        if local_name(child.tag) == name:
            return join_text_fragments(list(child.itertext()))
    return None


def join_text_fragments(parts: list[str]) -> str:
    joined = ""
    for part in parts:
        if not part:
            continue
        if joined and not joined[-1].isspace() and not part[0].isspace():
            if joined[-1].isalnum() and part[0].isalnum():
                joined += " "
        joined += part
    return clean_text(joined)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
