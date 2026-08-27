from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from ..academic.matching import AcademicLexicalMatcher
from ..classification.semantic import (
    ClassificationResult,
    SemanticClassificationPipeline,
    rejected_lexical,
)
from ..http import HttpClient
from ..models import NormalizedItem, to_iso8601
from .common import SourceRunResult, initialize_result
from .project_pages import LinkRecord, extract_research_links, project_item_from_url


@dataclass(slots=True, frozen=True)
class CVFIndexPaper:
    source_id: str
    title: str
    authors: list[str]
    detail_url: str


@dataclass(slots=True, frozen=True)
class CVFPaperDetail:
    title: str
    authors: list[str]
    abstract: str
    links: list[LinkRecord]
    pdf_url: str | None
    supplemental_url: str | None
    bibtex_url: str | None


class CVFCollector:
    def __init__(
        self,
        client: HttpClient,
        state: dict[str, Any],
        config: dict[str, Any],
        taxonomy: dict[str, Any],
        classifier: SemanticClassificationPipeline | None = None,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.state = state
        self.config = config
        self.matcher = AcademicLexicalMatcher(taxonomy, config["matching"])
        self.classifier = classifier
        self.sleeper = sleeper
        self.monotonic = monotonic
        self._last_request_at: float | None = None

    def collect(self, run_at: datetime) -> SourceRunResult:
        run_at = run_at.astimezone(UTC)
        result = initialize_result()
        cvf_state = (
            self.state.setdefault("sources", {}).setdefault("cvf", {}).setdefault("editions", {})
        )

        for edition in self.config["cvf"]["editions"]:
            if not edition.get("enabled", True):
                continue
            try:
                papers = self._collect_index(edition)
                minimum = int(edition["minimum_index_papers"])
                if len(papers) < minimum:
                    raise ValueError(
                        f"CVF edition {edition['id']} yielded {len(papers)} papers; expected at least {minimum}"
                    )
                edition_state = cvf_state.setdefault(edition["id"], {})
                known = set(edition_state.get("paper_ids", []))
                previous_active = set(edition_state.get("active_paper_ids", known))
                current = set(papers)
                bootstrapped = bool(edition_state.get("bootstrapped"))
                missing = sorted(previous_active - current) if bootstrapped else []
                if missing:
                    self._guard_inventory_loss(edition, previous_active, current, missing)
                    result.add_warning(
                        f"cvf:{edition['id']}",
                        f"CVF edition {edition['id']} removed {len(missing)} previously active "
                        f"paper IDs: previous_active={len(previous_active)}, current={len(current)}, "
                        f"missing_ids={missing}",
                    )
                new_ids = sorted(current - known) if bootstrapped else []

                for source_id in new_ids:
                    paper = papers[source_id]
                    detail = self._collect_detail(paper.detail_url)
                    item = self._normalize_paper(paper, detail, edition, run_at)
                    if item is None:
                        continue
                    result.items.append(item)
                    for project_url in item.metadata.get("project_urls", []):
                        result.items.append(project_item_from_url(item, project_url))

                edition_state["paper_ids"] = sorted(known | current)
                edition_state["active_paper_ids"] = sorted(current)
                edition_state["bootstrapped"] = True
                edition_state["last_seen_at"] = to_iso8601(run_at)
            except Exception as exc:
                result.add_error(f"cvf:{edition['id']}", exc)

        result.items.sort(key=lambda item: (item.kind, item.source_id))
        return result

    def _guard_inventory_loss(
        self,
        edition: dict[str, Any],
        previous_active: set[str],
        current: set[str],
        missing: list[str],
    ) -> None:
        guard = self.config["cvf"]["inventory_loss_guard"]
        fraction_limit = float(guard["maximum_fraction"])
        minimum_tolerance = int(guard["minimum_tolerance"])
        allowed_missing = max(
            minimum_tolerance,
            math.ceil(len(previous_active) * fraction_limit),
        )
        if len(missing) <= allowed_missing:
            return

        raise ValueError(
            f"CVF edition {edition['id']} inventory loss exceeded guard: "
            f"previous_active={len(previous_active)}, current={len(current)}, "
            f"missing={len(missing)}, allowed_missing={allowed_missing}, "
            f"missing_ids={missing}"
        )

    def _collect_index(self, edition: dict[str, Any]) -> dict[str, CVFIndexPaper]:
        papers: dict[str, CVFIndexPaper] = {}
        for path in edition["index_paths"]:
            self._pace()
            response = self.client.get_text(path, accept="text/html")
            parsed = parse_cvf_index(response.data, self.config["cvf"]["base_url"])
            papers.update({paper.source_id: paper for paper in parsed})
        return papers

    def _collect_detail(self, url: str) -> CVFPaperDetail:
        self._pace()
        response = self.client.get_text(url, accept="text/html")
        return parse_cvf_detail(response.data, url)

    def _normalize_paper(
        self,
        paper: CVFIndexPaper,
        detail: CVFPaperDetail,
        edition: dict[str, Any],
        run_at: datetime,
    ) -> NormalizedItem | None:
        title = detail.title or paper.title
        authors = detail.authors or paper.authors
        match = self.matcher.match(title, detail.abstract)
        threshold = float(self.config["matching"]["minimum_relevance_score"])
        classification = self._classify(title, detail.abstract, match, threshold)
        if not classification.accepted:
            return None

        extracted = extract_research_links(detail.links, base_url=paper.detail_url)
        return NormalizedItem(
            id=f"cvf:paper:{paper.source_id}",
            source="cvf",
            source_id=paper.source_id,
            kind="paper",
            title=title,
            url=paper.detail_url,
            discovered_at=to_iso8601(run_at),
            summary=detail.abstract or None,
            authors=authors,
            venue=edition["venue"],
            topics=classification.topics,
            matched_terms=classification.matched_terms,
            scores={"relevance": classification.relevance},
            metadata={
                "action": "discovered",
                "venue_year": edition["year"],
                "edition_id": edition["id"],
                "pdf_url": detail.pdf_url,
                "supplemental_url": detail.supplemental_url,
                "bibtex_url": detail.bibtex_url,
                "project_urls": extracted.project_urls,
                "code_urls": extracted.code_urls,
                "external_urls": extracted.external_urls,
                "classification": classification.evidence,
            },
        )

    def _classify(
        self, title: str, abstract: str, match: Any, threshold: float
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
            text=abstract,
            lexical_score=match.score,
            lexical_topics=match.topics,
            matched_terms=match.matched_terms,
            lexical_threshold=threshold,
        )

    def _pace(self) -> None:
        interval = float(self.config["cvf"]["request_interval_seconds"])
        if self._last_request_at is not None:
            wait = interval - (self.monotonic() - self._last_request_at)
            if wait > 0:
                self.sleeper(wait)
        self._last_request_at = self.monotonic()


class _CVFIndexParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.papers: list[CVFIndexPaper] = []
        self._in_title = False
        self._title_parts: list[str] = []
        self._detail_href: str | None = None
        self._capture_authors = False
        self._author_parts: list[str] = []
        self._author_anchor_parts: list[str] = []
        self._in_author_anchor = False
        self._pending: tuple[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "dt" and "ptitle" in classes:
            self._in_title = True
            self._title_parts = []
            self._detail_href = None
        elif self._in_title and tag == "a" and attributes.get("href"):
            self._detail_href = attributes["href"]
        elif self._capture_authors and tag == "a":
            self._in_author_anchor = True
            self._author_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "dt" and self._in_title:
            self._in_title = False
            title = clean_text(" ".join(self._title_parts))
            if title and self._detail_href:
                self._pending = (title, self._detail_href)
                self._capture_authors = True
                self._author_parts = []
                self._author_anchor_parts = []
        elif tag == "a" and self._capture_authors and self._in_author_anchor:
            self._in_author_anchor = False
            author = clean_text(" ".join(self._author_parts))
            if author:
                self._author_anchor_parts.append(author)
        elif tag == "dd" and self._capture_authors and self._pending:
            title, href = self._pending
            author_text = clean_text(" ".join(self._author_parts))
            authors = self._author_anchor_parts or split_authors(author_text)
            detail_url = urljoin(self.base_url, href)
            source_id = cvf_source_id(detail_url)
            if source_id:
                self.papers.append(CVFIndexPaper(source_id, title, authors, detail_url))
            self._pending = None
            self._capture_authors = False
            self._author_parts = []
            self._author_anchor_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        elif self._capture_authors:
            self._author_parts.append(data)


class _CVFDetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._section: str | None = None
        self._section_depth = 0
        self._text: dict[str, list[str]] = {"papertitle": [], "authors": [], "abstract": []}
        self._author_anchor_text: list[str] = []
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self.links: list[LinkRecord] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "div" and attributes.get("id") in self._text:
            self._section = str(attributes["id"])
            self._section_depth = 1
        elif self._section and tag == "div":
            self._section_depth += 1
        if tag == "a" and attributes.get("href"):
            self._anchor_href = attributes["href"]
            self._anchor_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor_href is not None:
            text = clean_text(" ".join(self._anchor_text))
            context = self._section or "page"
            self.links.append(LinkRecord(self._anchor_href, text, context))
            if self._section == "authors" and text:
                self._author_anchor_text.append(text)
            self._anchor_href = None
            self._anchor_text = []
        if tag == "div" and self._section:
            self._section_depth -= 1
            if self._section_depth <= 0:
                self._section = None
                self._section_depth = 0

    def handle_data(self, data: str) -> None:
        if self._section:
            self._text[self._section].append(data)
        if self._anchor_href is not None:
            self._anchor_text.append(data)

    def detail(self, base_url: str) -> CVFPaperDetail:
        title = clean_text(" ".join(self._text["papertitle"]))
        author_text = clean_text(" ".join(self._text["authors"]))
        authors = self._author_anchor_text or split_authors(author_text)
        abstract = clean_text(" ".join(self._text["abstract"]))
        absolute_links = [
            LinkRecord(urljoin(base_url, link.href), link.text, link.context) for link in self.links
        ]
        pdf = first_link(
            absolute_links,
            lambda link: (
                link.text.casefold() == "pdf"
                or ("/papers/" in link.href and link.href.endswith(".pdf"))
            ),
        )
        supplemental = first_link(
            absolute_links,
            lambda link: "supp" in link.text.casefold() or "/supplemental/" in link.href,
        )
        bibtex = first_link(
            absolute_links, lambda link: "bib" in link.text.casefold() or "/bibtex/" in link.href
        )
        return CVFPaperDetail(title, authors, abstract, absolute_links, pdf, supplemental, bibtex)


def parse_cvf_index(html: str, base_url: str) -> list[CVFIndexPaper]:
    parser = _CVFIndexParser(base_url)
    parser.feed(html)
    return parser.papers


def parse_cvf_detail(html: str, base_url: str) -> CVFPaperDetail:
    parser = _CVFDetailParser()
    parser.feed(html)
    return parser.detail(base_url)


def cvf_source_id(url: str) -> str | None:
    parsed = urlsplit(url)
    path = parsed.path.strip("/")
    return path or None


def split_authors(value: str) -> list[str]:
    return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]


def clean_text(value: str) -> str:
    return " ".join(value.split())


def first_link(links: list[LinkRecord], predicate: Callable[[LinkRecord], bool]) -> str | None:
    for link in links:
        if predicate(link):
            return link.href
    return None
