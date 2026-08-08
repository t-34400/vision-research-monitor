from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from ..models import NormalizedItem, to_iso8601
from .common import AcademicCoverageError, AcademicRunResult, collection_window, initialize_result, normalize_window
from .http import AcademicHttpClient
from .matching import AcademicLexicalMatcher, contains_normalized, normalize_text

ATOM = "http://www.w3.org/2005/Atom"
ARXIV = "http://arxiv.org/schemas/atom"


@dataclass(slots=True)
class ArxivPaper:
    source_id: str
    versioned_id: str
    title: str
    abstract: str
    authors: list[str]
    categories: list[str]
    primary_category: str | None
    published_at: str | None
    updated_at: str | None
    url: str
    pdf_url: str | None
    comment: str | None
    journal_ref: str | None
    doi: str | None


class ArxivCollector:
    def __init__(
        self,
        client: AcademicHttpClient,
        state: dict[str, Any],
        config: dict[str, Any],
        taxonomy: dict[str, Any],
        venues: dict[str, Any],
        *,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.state = state
        self.config = config
        self.matcher = AcademicLexicalMatcher(taxonomy, config["matching"])
        self.venues = venues
        self.sleeper = sleeper
        self.monotonic = monotonic
        self._last_request_at: float | None = None

    def collection_window(self, run_at: datetime) -> tuple[datetime, datetime]:
        arxiv_state = self.state.setdefault("academic", {}).setdefault("arxiv", {})
        return collection_window(
            run_at,
            arxiv_state.get("last_successful_at"),
            self.config["window"],
            source_name="arXiv",
        )

    def collect(
        self,
        run_at: datetime,
        *,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> AcademicRunResult:
        run_at = run_at.astimezone(timezone.utc)
        if window_start is None or window_end is None:
            window_start, window_end = self.collection_window(run_at)
        window_start, window_end = normalize_window(window_start, window_end)
        result = initialize_result(window_start, window_end)
        papers: dict[str, ArxivPaper] = {}

        for category in self.config["arxiv"]["categories"]:
            try:
                for paper in self._collect_category(category, window_start, window_end):
                    current = papers.get(paper.source_id)
                    papers[paper.source_id] = merge_papers(current, paper) if current else paper
            except Exception as exc:
                result.add_error(f"arxiv:{category}", exc)

        threshold = float(self.config["matching"]["minimum_relevance_score"])
        for paper in papers.values():
            match = self.matcher.match(paper.title, paper.abstract)
            if match.score < threshold:
                continue
            result.items.append(self._normalize(paper, match.score, match.topics, match.matched_terms, run_at))

        result.items.sort(key=lambda item: (item.published_at or "", item.source_id))
        return result

    def _collect_category(self, category: str, start: datetime, end: datetime) -> list[ArxivPaper]:
        page_size = int(self.config["arxiv"]["page_size"])
        maximum = int(self.config["arxiv"]["max_results_per_category"])
        query = f"cat:{category} AND submittedDate:[{format_arxiv_date(start)} TO {format_arxiv_date(end)}]"
        found: list[ArxivPaper] = []
        offset = 0

        while offset < maximum:
            self._pace()
            response = self.client.get_text(
                "/api/query",
                params={
                    "search_query": query,
                    "start": offset,
                    "max_results": min(page_size, maximum - offset),
                    "sortBy": "submittedDate",
                    "sortOrder": "ascending",
                },
            )
            batch, total = parse_arxiv_feed(response.data)
            found.extend(batch)
            offset += len(batch)
            if not batch or offset >= total:
                return found
            if offset >= maximum:
                raise AcademicCoverageError(
                    f"arXiv category {category} returned more than the configured {maximum} results"
                )
        return found

    def _pace(self) -> None:
        interval = float(self.config["arxiv"]["request_interval_seconds"])
        if self._last_request_at is not None:
            wait = interval - (self.monotonic() - self._last_request_at)
            if wait > 0:
                self.sleeper(wait)
        self._last_request_at = self.monotonic()

    def _normalize(
        self,
        paper: ArxivPaper,
        score: float,
        topics: list[str],
        matched_terms: list[str],
        run_at: datetime,
    ) -> NormalizedItem:
        venue = infer_venue(paper, self.venues)
        return NormalizedItem(
            id=f"arxiv:paper:{paper.source_id}",
            source="arxiv",
            source_id=paper.source_id,
            kind="paper",
            title=paper.title,
            url=paper.url,
            discovered_at=to_iso8601(run_at),
            published_at=paper.published_at,
            updated_at=paper.updated_at,
            summary=paper.abstract,
            authors=paper.authors,
            venue=venue,
            topics=topics,
            matched_terms=matched_terms,
            scores={"relevance": score},
            metadata={
                "versioned_id": paper.versioned_id,
                "categories": paper.categories,
                "primary_category": paper.primary_category,
                "comment": paper.comment,
                "journal_ref": paper.journal_ref,
                "doi": paper.doi,
                "pdf_url": paper.pdf_url,
            },
        )


def parse_arxiv_feed(xml: str) -> tuple[list[ArxivPaper], int]:
    root = ET.fromstring(xml)
    total_node = root.find("{http://a9.com/-/spec/opensearch/1.1/}totalResults")
    total = int(total_node.text or "0") if total_node is not None else 0
    papers: list[ArxivPaper] = []
    for entry in root.findall(f"{{{ATOM}}}entry"):
        raw_id = _text(entry, ATOM, "id") or ""
        versioned_id = raw_id.rsplit("/", 1)[-1]
        source_id = re.sub(r"v\d+$", "", versioned_id)
        links = entry.findall(f"{{{ATOM}}}link")
        url = next(
            (link.attrib.get("href", "") for link in links if link.attrib.get("rel") == "alternate"),
            f"https://arxiv.org/abs/{source_id}",
        )
        pdf_url = next(
            (
                link.attrib.get("href")
                for link in links
                if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf"
            ),
            None,
        )
        categories = [node.attrib["term"] for node in entry.findall(f"{{{ATOM}}}category") if node.attrib.get("term")]
        primary = entry.find(f"{{{ARXIV}}}primary_category")
        papers.append(
            ArxivPaper(
                source_id=source_id,
                versioned_id=versioned_id,
                title=clean_whitespace(_text(entry, ATOM, "title") or ""),
                abstract=clean_whitespace(_text(entry, ATOM, "summary") or ""),
                authors=[
                    clean_whitespace(_text(author, ATOM, "name") or "")
                    for author in entry.findall(f"{{{ATOM}}}author")
                    if clean_whitespace(_text(author, ATOM, "name") or "")
                ],
                categories=categories,
                primary_category=primary.attrib.get("term") if primary is not None else None,
                published_at=normalize_atom_time(_text(entry, ATOM, "published")),
                updated_at=normalize_atom_time(_text(entry, ATOM, "updated")),
                url=url,
                pdf_url=pdf_url,
                comment=clean_optional(_text(entry, ARXIV, "comment")),
                journal_ref=clean_optional(_text(entry, ARXIV, "journal_ref")),
                doi=clean_optional(_text(entry, ARXIV, "doi")),
            )
        )
    return papers, total


def merge_papers(existing: ArxivPaper, incoming: ArxivPaper) -> ArxivPaper:
    categories = list(dict.fromkeys(existing.categories + incoming.categories))
    existing.categories = categories
    if incoming.updated_at and (not existing.updated_at or incoming.updated_at > existing.updated_at):
        existing.versioned_id = incoming.versioned_id
        existing.updated_at = incoming.updated_at
    return existing


def infer_venue(paper: ArxivPaper, venues: dict[str, Any]) -> str | None:
    haystack = normalize_text(" ".join(value for value in [paper.comment, paper.journal_ref] if value))
    if not haystack:
        return None
    for venue in venues["venues"]:
        for alias in venue["aliases"]:
            normalized = normalize_text(alias)
            if len(normalized.replace(" ", "")) >= 3 and contains_normalized(haystack, normalized):
                return venue["id"]
    return None


def format_arxiv_date(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%d%H%M")


def normalize_atom_time(value: str | None) -> str | None:
    if not value:
        return None
    return to_iso8601(datetime.fromisoformat(value.replace("Z", "+00:00")))


def clean_whitespace(value: str) -> str:
    return " ".join(value.split())


def clean_optional(value: str | None) -> str | None:
    cleaned = clean_whitespace(value or "")
    return cleaned or None


def _text(node: ET.Element, namespace: str, name: str) -> str | None:
    child = node.find(f"{{{namespace}}}{name}")
    return child.text if child is not None else None
