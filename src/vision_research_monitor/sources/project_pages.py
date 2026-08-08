from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from ..linking.normalize import canonicalize_url
from ..models import NormalizedItem


@dataclass(slots=True, frozen=True)
class LinkRecord:
    href: str
    text: str = ""
    context: str = ""


@dataclass(slots=True, frozen=True)
class ExtractedLinks:
    project_urls: list[str]
    code_urls: list[str]
    external_urls: list[str]


_CODE_HOSTS = {"github.com", "gitlab.com", "codeberg.org", "bitbucket.org"}
_IGNORED_HOSTS = {
    "arxiv.org",
    "doi.org",
    "openreview.net",
    "openaccess.thecvf.com",
    "thecvf.com",
    "ieeexplore.ieee.org",
}
_PROJECT_LABELS = ("project", "homepage", "website", "webpage", "demo", "interactive")
_CODE_LABELS = ("code", "repository", "repo", "github", "gitlab")


def extract_research_links(records: list[LinkRecord], *, base_url: str) -> ExtractedLinks:
    projects: set[str] = set()
    code: set[str] = set()
    external: set[str] = set()

    for record in records:
        raw = record.href.strip()
        if not raw or raw.startswith(("mailto:", "javascript:", "#")):
            continue
        absolute = urljoin(base_url, raw)
        canonical = canonicalize_url(absolute, tracking_query_prefixes=("utm_",), tracking_query_keys=("ref", "source"))
        if canonical is None:
            continue
        host = (urlsplit(canonical).hostname or "").casefold()
        if host.startswith("www."):
            host = host[4:]
        if host in _IGNORED_HOSTS:
            continue

        label = f"{record.text} {record.context}".casefold()
        external.add(canonical)
        if host in _CODE_HOSTS or any(token in label for token in _CODE_LABELS):
            code.add(canonical)
            continue
        if any(token in label for token in _PROJECT_LABELS) or record.context == "abstract":
            projects.add(canonical)

    return ExtractedLinks(sorted(projects), sorted(code), sorted(external))


def project_item_from_url(parent: NormalizedItem, url: str) -> NormalizedItem:
    digest = hashlib.sha256(f"{parent.id}\n{url}".encode("utf-8")).hexdigest()[:20]
    source_id = f"{parent.source_id}:project:{digest}"
    return NormalizedItem(
        id=f"{parent.source}:project:{digest}",
        source=parent.source,
        source_id=source_id,
        kind="project",
        title=f"Project page — {parent.title}",
        url=url,
        discovered_at=parent.discovered_at,
        published_at=parent.published_at,
        updated_at=parent.updated_at,
        summary=parent.summary,
        authors=list(parent.authors),
        organization=parent.organization,
        venue=parent.venue,
        topics=list(parent.topics),
        matched_terms=list(parent.matched_terms),
        priority=dict(parent.priority),
        scores=dict(parent.scores),
        related_items=[parent.id],
        metadata={
            "action": "discovered",
            "parent_item_id": parent.id,
            "parent_source_id": parent.source_id,
            "discovery_source": parent.source,
            "reportable": False,
        },
    )
