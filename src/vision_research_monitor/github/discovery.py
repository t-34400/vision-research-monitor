from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from ..classification.semantic import ClassificationResult, SemanticClassificationPipeline, rejected_lexical
from ..models import NormalizedItem, parse_iso8601, to_iso8601
from .client import GitHubApiError, GitHubClient, GitHubNotFoundError


class DiscoveryCoverageError(GitHubApiError):
    pass


@dataclass(slots=True)
class DiscoveryRunResult:
    items: list[NormalizedItem] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    failed_queries: int = 0
    window_start: str | None = None
    window_end: str | None = None

    def add_error(self, target: str, exc: Exception) -> None:
        self.failed_queries += 1
        self.diagnostics.append({"level": "error", "target": target, "message": str(exc)})

    def add_warning(self, target: str, message: str) -> None:
        self.diagnostics.append({"level": "warning", "target": target, "message": message})


@dataclass(slots=True)
class Candidate:
    repository: dict[str, Any]
    query_topics: set[str] = field(default_factory=set)
    query_terms: set[str] = field(default_factory=set)
    query_ids: set[str] = field(default_factory=set)
    families: set[str] = field(default_factory=set)
    modes: set[str] = field(default_factory=set)
    venue_hits: set[tuple[str, int, str]] = field(default_factory=set)


@dataclass(slots=True)
class LexicalMatch:
    score: float
    topics: list[str]
    matched_terms: list[str]


class LexicalScorer:
    def __init__(self, taxonomy: dict[str, Any]) -> None:
        self._aliases: dict[str, list[tuple[str, str]]] = {}
        for topic in taxonomy["topics"]:
            aliases: list[tuple[str, str]] = []
            for alias in topic["aliases"]:
                normalized = normalize_text(alias)
                if normalized:
                    aliases.append((alias, normalized))
            self._aliases[topic["id"]] = aliases

    def score(
        self,
        repository: dict[str, Any],
        *,
        query_topics: set[str],
        query_terms: set[str],
        readme: str | None = None,
    ) -> LexicalMatch:
        fields = {
            "name": normalize_text(repository.get("full_name") or repository.get("name") or ""),
            "description": normalize_text(repository.get("description") or ""),
            "topics": normalize_text(" ".join(repository.get("topics") or [])),
            "readme": normalize_text((readme or "")[:200_000]),
        }
        field_weights = {"name": 0.35, "description": 0.25, "topics": 0.30, "readme": 0.20}
        topic_scores: dict[str, float] = {topic_id: 0.35 for topic_id in query_topics}
        matched_terms = set(query_terms)

        for topic_id, aliases in self._aliases.items():
            best = 0.0
            best_term: str | None = None
            for original, alias in aliases:
                for field_name, field_value in fields.items():
                    if alias and contains_normalized(field_value, alias) and field_weights[field_name] > best:
                        best = field_weights[field_name]
                        best_term = original
            if best:
                topic_scores[topic_id] = max(topic_scores.get(topic_id, 0.0), best)
                if best_term:
                    matched_terms.add(best_term)

        if not topic_scores:
            return LexicalMatch(0.0, [], sorted(matched_terms, key=str.casefold))

        ordered_scores = sorted(topic_scores.values(), reverse=True)
        score = ordered_scores[0]
        if len(ordered_scores) > 1:
            score += min(0.20, sum(ordered_scores[1:]) * 0.10)
        if query_topics and any(topic_id in topic_scores and topic_scores[topic_id] > 0.35 for topic_id in query_topics):
            score += 0.10
        return LexicalMatch(min(1.0, round(score, 4)), sorted(topic_scores), sorted(matched_terms, key=str.casefold))


class GitHubDiscoveryCollector:
    def __init__(
        self,
        client: GitHubClient,
        state: dict[str, Any],
        config: dict[str, Any],
        taxonomy: dict[str, Any],
        venues: dict[str, Any],
        classifier: SemanticClassificationPipeline | None = None,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.state = state
        self.config = config
        self.taxonomy = taxonomy
        self.venues = venues
        self.scorer = LexicalScorer(taxonomy)
        self.classifier = classifier
        self.sleeper = sleeper
        self.monotonic = monotonic
        self._last_search_request_at: float | None = None
        self._readme_enrichments = 0

    def collection_window(self, run_at: datetime) -> tuple[datetime, datetime]:
        run_at = run_at.astimezone(timezone.utc)
        window = self.config["window"]
        previous = parse_iso8601(self.state.get("last_successful_at"))
        if previous is None:
            return run_at - timedelta(hours=window["initial_lookback_hours"]), run_at

        elapsed = run_at - previous
        if elapsed > timedelta(hours=window["max_catchup_hours"]):
            raise DiscoveryCoverageError(
                f"GitHub discovery checkpoint is {elapsed.total_seconds() / 3600:.1f} hours old; "
                f"maximum automatic catch-up is {window['max_catchup_hours']} hours"
            )
        return previous - timedelta(minutes=window["overlap_minutes"]), run_at

    def collect(
        self,
        run_at: datetime,
        *,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> DiscoveryRunResult:
        run_at = run_at.astimezone(timezone.utc)
        if window_start is None or window_end is None:
            window_start, window_end = self.collection_window(run_at)
        else:
            window_start = window_start.astimezone(timezone.utc)
            window_end = window_end.astimezone(timezone.utc)
        if window_start >= window_end:
            raise ValueError("GitHub discovery window start must be before its end")

        result = DiscoveryRunResult(window_start=to_iso8601(window_start), window_end=to_iso8601(window_end))
        candidates: dict[str, Candidate] = {}

        for family in self.config["query_families"]:
            for query in family["queries"]:
                modes = query.get("modes", ["created", "pushed"])
                for mode in modes:
                    target = f"topic:{family['id']}:{query['id']}:{mode}"
                    try:
                        repositories = self._search_query(query["text"], mode, window_start, window_end)
                    except Exception as exc:
                        result.add_error(target, exc)
                        continue
                    for repository in repositories:
                        candidate = candidates.setdefault(str(repository["id"]), Candidate(repository=repository))
                        candidate.repository = prefer_repository(candidate.repository, repository)
                        candidate.query_topics.update(query["topics"])
                        candidate.query_terms.add(unquote_query_term(query["text"]))
                        candidate.query_ids.add(query["id"])
                        candidate.families.add(family["id"])
                        candidate.modes.add(mode)

        self._collect_venue_candidates(candidates, window_start, window_end, run_at, result)
        result.items = self._normalize_candidates(candidates, run_at, result)
        return result

    def _collect_venue_candidates(
        self,
        candidates: dict[str, Candidate],
        window_start: datetime,
        window_end: datetime,
        run_at: datetime,
        result: DiscoveryRunResult,
    ) -> None:
        venue_config = self.config["venue_search"]
        if not venue_config.get("enabled", True):
            return
        allowed_ids = set(venue_config.get("venue_ids", []))
        priorities = set(venue_config["priorities"])
        current_year = run_at.astimezone(ZoneInfo("Asia/Tokyo")).year
        years = [current_year + offset for offset in venue_config["year_offsets"]]

        for venue in self.venues["venues"]:
            if allowed_ids and venue["id"] not in allowed_ids:
                continue
            if venue["priority"] not in priorities:
                continue
            alias = venue["aliases"][0]
            for year in years:
                query = f'"{alias} {year}" in:readme'
                for mode in venue_config["modes"]:
                    target = f"venue:{venue['id']}:{year}:{mode}"
                    try:
                        repositories = self._search_query(query, mode, window_start, window_end, add_locations=False)
                    except Exception as exc:
                        result.add_error(target, exc)
                        continue
                    for repository in repositories:
                        candidate = candidates.setdefault(str(repository["id"]), Candidate(repository=repository))
                        candidate.repository = prefer_repository(candidate.repository, repository)
                        candidate.venue_hits.add((venue["id"], year, alias))
                        candidate.modes.add(mode)

    def _search_query(
        self,
        base_query: str,
        mode: str,
        start: datetime,
        end: datetime,
        *,
        add_locations: bool = True,
    ) -> list[dict[str, Any]]:
        common = self.config["search"]
        qualifiers: list[str] = []
        if add_locations:
            qualifiers.append(f"in:{','.join(common['locations'])}")
        if common["public_only"]:
            qualifiers.append("is:public")
        if common["exclude_archived"]:
            qualifiers.append("archived:false")
        if mode == "pushed" and common["pushed_minimum_stars"]:
            qualifiers.append(f"stars:>={common['pushed_minimum_stars']}")
        prefix = " ".join([base_query, *qualifiers])
        return self._search_slice(prefix, mode, start, end)

    def _search_slice(
        self,
        prefix: str,
        mode: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        search = self.config["search"]
        per_page = search["per_page"]
        max_pages = search["max_pages_per_slice"]
        q = f"{prefix} {mode}:{search_time(start)}..{search_time(end)}"
        first = self._search_page(q, 1, per_page)
        total_count, incomplete, first_items = parse_search_response(first, q)
        capacity = per_page * max_pages

        if incomplete or total_count > capacity:
            minimum = timedelta(minutes=self.config["window"]["minimum_split_minutes"])
            if end - start <= minimum:
                reason = "incomplete search results" if incomplete else f"{total_count} results exceed slice capacity {capacity}"
                raise DiscoveryCoverageError(f"Cannot safely collect {q}: {reason}")
            midpoint = start + (end - start) / 2
            left = self._search_slice(prefix, mode, start, midpoint)
            right = self._search_slice(prefix, mode, midpoint, end)
            return dedupe_repositories([*left, *right])

        pages = max(1, math.ceil(total_count / per_page))
        repositories = first_items
        for page in range(2, pages + 1):
            data = self._search_page(q, page, per_page)
            _, page_incomplete, page_items = parse_search_response(data, q)
            if page_incomplete:
                raise DiscoveryCoverageError(f"GitHub returned incomplete results for {q} page {page}")
            repositories.extend(page_items)
        return dedupe_repositories(repositories)

    def _search_page(self, query: str, page: int, per_page: int) -> dict[str, Any]:
        self._pace_search()
        result = self.client.get_json(
            "/search/repositories",
            params={"q": query, "per_page": per_page, "page": page},
        )
        if not isinstance(result.data, dict):
            raise GitHubApiError("Expected object response from /search/repositories")
        return result.data

    def _pace_search(self) -> None:
        interval = float(self.config["search"]["request_interval_seconds"])
        if interval <= 0:
            return
        now = self.monotonic()
        if self._last_search_request_at is not None:
            remaining = interval - (now - self._last_search_request_at)
            if remaining > 0:
                self.sleeper(remaining)
                now = self.monotonic()
        self._last_search_request_at = now

    def _normalize_candidates(
        self,
        candidates: dict[str, Candidate],
        run_at: datetime,
        result: DiscoveryRunResult,
    ) -> list[NormalizedItem]:
        search = self.config["search"]
        items: list[NormalizedItem] = []
        for candidate in candidates.values():
            readme: str | None = None
            lexical = self.scorer.score(
                candidate.repository,
                query_topics=candidate.query_topics,
                query_terms=candidate.query_terms,
            )
            is_venue_only = not candidate.query_topics and bool(candidate.venue_hits)
            if is_venue_only and not lexical.topics:
                readme = self._readme_for_candidate(candidate, result)
                if readme is not None:
                    lexical = self.scorer.score(
                        candidate.repository,
                        query_topics=candidate.query_topics,
                        query_terms=candidate.query_terms,
                        readme=readme,
                    )

            threshold = (
                search["minimum_venue_relevance_score"]
                if is_venue_only
                else search["minimum_topic_relevance_score"]
            )
            classification = self._classify_candidate(candidate, lexical, threshold, readme)
            if not classification.accepted:
                continue
            items.append(self._repository_item(candidate, classification, run_at))
        return sorted(items, key=lambda item: (-float(item.scores.get("relevance") or 0), item.title.casefold()))

    def _classify_candidate(
        self,
        candidate: Candidate,
        lexical: LexicalMatch,
        threshold: float,
        readme: str | None,
    ) -> ClassificationResult:
        if self.classifier is None:
            if lexical.score < threshold:
                return rejected_lexical(lexical.score, lexical.topics, lexical.matched_terms)
            return ClassificationResult(
                accepted=True,
                relevance=lexical.score,
                topics=lexical.topics,
                matched_terms=lexical.matched_terms,
                evidence={
                    "method": "lexical",
                    "lexical_score": lexical.score,
                    "semantic_model": None,
                    "llm_model": None,
                },
            )
        repository = candidate.repository
        text = " ".join(
            value
            for value in [
                str(repository.get("description") or ""),
                " ".join(repository.get("topics") or []),
                readme or "",
            ]
            if value
        )
        return self.classifier.classify(
            title=str(repository.get("full_name") or repository.get("name") or ""),
            text=text,
            lexical_score=lexical.score,
            lexical_topics=lexical.topics,
            matched_terms=lexical.matched_terms,
            lexical_threshold=threshold,
        )

    def _readme_for_candidate(self, candidate: Candidate, result: DiscoveryRunResult) -> str | None:
        limit = self.config["search"]["max_readme_enrichments_per_run"]
        if self._readme_enrichments >= limit:
            result.add_warning("venue-readme", f"README enrichment cap of {limit} reached; remaining venue-only candidates were skipped")
            return None
        self._readme_enrichments += 1
        full_name = candidate.repository.get("full_name")
        if not full_name:
            return None
        try:
            response = self.client.get_text(f"/repos/{full_name}/readme")
        except GitHubNotFoundError:
            return None
        except GitHubApiError as exc:
            result.add_warning(f"readme:{full_name}", str(exc))
            return None
        return response.data if isinstance(response.data, str) else None

    @staticmethod
    def _repository_item(candidate: Candidate, classification: ClassificationResult, run_at: datetime) -> NormalizedItem:
        repo = candidate.repository
        repo_id = str(repo["id"])
        venue_hits = [
            {"venue": venue_id, "year": year, "alias": alias}
            for venue_id, year, alias in sorted(candidate.venue_hits)
        ]
        return NormalizedItem(
            id=f"github:repository:{repo_id}",
            source="github",
            source_id=repo_id,
            kind="repository",
            title=repo["full_name"],
            url=repo["html_url"],
            summary=repo.get("description"),
            organization=owner_login(repo),
            published_at=repo.get("created_at"),
            updated_at=repo.get("updated_at") or repo.get("pushed_at"),
            discovered_at=to_iso8601(run_at),
            topics=classification.topics,
            matched_terms=classification.matched_terms,
            priority={"source": 0.0},
            scores={"relevance": classification.relevance},
            metadata={
                "action": "discovered",
                "discovery_modes": sorted(candidate.modes),
                "query_ids": sorted(candidate.query_ids),
                "query_families": sorted(candidate.families),
                "venue_hits": venue_hits,
                "github_topics": sorted(repo.get("topics") or []),
                "homepage": repo.get("homepage"),
                "stars": int(repo.get("stargazers_count") or 0),
                "stars_delta": 0,
                "forks": int(repo.get("forks_count") or 0),
                "language": repo.get("language"),
                "fork": bool(repo.get("fork")),
                "archived": bool(repo.get("archived")),
                "classification": classification.evidence,
            },
        )


def parse_search_response(data: dict[str, Any], query: str) -> tuple[int, bool, list[dict[str, Any]]]:
    total_count = data.get("total_count")
    items = data.get("items")
    if not isinstance(total_count, int) or not isinstance(items, list):
        raise GitHubApiError(f"Invalid GitHub repository search response for {query}")
    return total_count, bool(data.get("incomplete_results")), [item for item in items if isinstance(item, dict)]


def search_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def contains_normalized(text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text} "


def unquote_query_term(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] == '"':
        return stripped[1:-1]
    return stripped


def owner_login(repo: dict[str, Any]) -> str | None:
    owner = repo.get("owner") or {}
    if isinstance(owner, dict) and isinstance(owner.get("login"), str):
        return owner["login"]
    full_name = repo.get("full_name")
    if isinstance(full_name, str) and "/" in full_name:
        return full_name.split("/", 1)[0]
    return None


def dedupe_repositories(repositories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for repository in repositories:
        if "id" not in repository:
            continue
        key = str(repository["id"])
        by_id[key] = prefer_repository(by_id.get(key), repository)
    return list(by_id.values())


def prefer_repository(current: dict[str, Any] | None, candidate: dict[str, Any]) -> dict[str, Any]:
    if current is None:
        return candidate
    current_updated = parse_iso8601(current.get("updated_at"))
    candidate_updated = parse_iso8601(candidate.get("updated_at"))
    if candidate_updated and (current_updated is None or candidate_updated > current_updated):
        return candidate
    return current
