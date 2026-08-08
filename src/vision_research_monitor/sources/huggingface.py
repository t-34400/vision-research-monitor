from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from ..academic.matching import AcademicLexicalMatcher
from ..classification.semantic import (
    ClassificationResult,
    SemanticClassificationPipeline,
    rejected_lexical,
)
from ..http import HttpClient
from ..linking.normalize import extract_urls
from ..models import NormalizedItem, parse_iso8601, to_iso8601
from .common import (
    SourceCoverageError,
    SourceRunResult,
    collection_window,
    initialize_result,
    normalize_window,
)

_LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


class HuggingFaceCollector:
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
        self._model_card_fetches = 0

    def collection_window(self, run_at: datetime) -> tuple[datetime, datetime]:
        source_state = self.state.setdefault("sources", {}).setdefault("huggingface", {})
        return collection_window(
            run_at,
            source_state.get("last_successful_at"),
            self.config["window"],
            source_name="Hugging Face",
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
        candidates: dict[str, dict[str, Any]] = {}

        for query in self.config["huggingface"]["queries"]:
            if not query.get("enabled", True):
                continue
            try:
                for model in self._collect_query(query["text"], window_start, window_end):
                    model_id = string_value(model.get("id")) or string_value(model.get("modelId"))
                    if not model_id:
                        continue
                    current = candidates.get(model_id)
                    if current is None or model_last_modified(model) > model_last_modified(current):
                        candidates[model_id] = model
            except Exception as exc:
                result.add_error(f"huggingface:{query['id']}", exc)

        source_state = self.state.setdefault("sources", {}).setdefault("huggingface", {})
        repositories = source_state.setdefault("repositories", {})
        threshold = float(self.config["matching"]["minimum_relevance_score"])

        for model_id in sorted(candidates):
            model = candidates[model_id]
            last_modified = model_last_modified(model)
            if last_modified is None:
                result.add_warning(
                    f"huggingface:{model_id}",
                    "model result has no parseable lastModified timestamp",
                )
                continue
            previous = (
                repositories.get(model_id, {})
                if isinstance(repositories.get(model_id), dict)
                else {}
            )
            previous_modified = previous.get("last_modified")
            if previous_modified == to_iso8601(last_modified):
                continue

            text, tags = model_text(model)
            match = self.matcher.match(model_id, text, keywords=tags)
            model_card = ""
            if match.score < threshold and self._model_card_fetches < int(
                self.config["huggingface"]["max_model_cards_per_run"]
            ):
                self._model_card_fetches += 1
                try:
                    model_card = self._fetch_model_card(model_id)
                except Exception as exc:
                    result.add_warning(f"huggingface:{model_id}", f"model card unavailable: {exc}")
                if model_card:
                    text = f"{text}\n{model_card}"
                    match = self.matcher.match(model_id, text, keywords=tags)

            classification = self._classify(model_id, text, match, threshold)
            repositories[model_id] = {
                "last_modified": to_iso8601(last_modified),
                "last_seen_at": to_iso8601(run_at),
            }
            if not classification.accepted:
                continue

            action = "discovered" if not previous_modified else "updated"
            result.items.append(
                normalize_huggingface_model(
                    model,
                    model_id,
                    model_card,
                    classification,
                    run_at,
                    action,
                )
            )

        result.items.sort(key=lambda item: (item.updated_at or "", item.source_id))
        return result

    def _collect_query(self, query: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        page_size = int(self.config["huggingface"]["page_size"])
        max_pages = int(self.config["huggingface"]["max_pages_per_query"])
        path: str | None = "/api/models"
        params: dict[str, Any] | None = {
            "search": query,
            "sort": "lastModified",
            "direction": -1,
            "limit": page_size,
            "full": "true",
            "cardData": "true",
        }
        found: list[dict[str, Any]] = []

        for _ in range(max_pages):
            if path is None:
                return found
            self._pace()
            response = self.client.get_json(path, params=params)
            params = None
            payload = response.data
            if not isinstance(payload, list):
                raise SourceCoverageError("Hugging Face model search returned a non-list payload")

            oldest: datetime | None = None
            for model in payload:
                if not isinstance(model, dict):
                    continue
                modified = model_last_modified(model)
                if modified is None:
                    continue
                if oldest is None or modified < oldest:
                    oldest = modified
                if start <= modified <= end:
                    found.append(model)

            if not payload or (oldest is not None and oldest < start):
                return found
            path = next_link(response.headers.get("link"))
            if path is None:
                return found

        raise SourceCoverageError(
            f"Hugging Face query {query!r} exceeded {max_pages} pages before crossing the collection window"
        )

    def _fetch_model_card(self, model_id: str) -> str:
        self._pace()
        response = self.client.get_text(
            f"https://huggingface.co/{model_id}/raw/main/README.md",
            accept="text/markdown, text/plain;q=0.9",
        )
        return response.data

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

    def _pace(self) -> None:
        interval = float(self.config["huggingface"]["request_interval_seconds"])
        if self._last_request_at is not None:
            wait = interval - (self.monotonic() - self._last_request_at)
            if wait > 0:
                self.sleeper(wait)
        self._last_request_at = self.monotonic()


def normalize_huggingface_model(
    model: dict[str, Any],
    model_id: str,
    model_card: str,
    classification: ClassificationResult,
    run_at: datetime,
    action: str,
) -> NormalizedItem:
    modified = model_last_modified(model)
    if modified is None:
        raise ValueError(f"Hugging Face model {model_id} is missing lastModified")
    created = parse_hf_datetime(model.get("createdAt") or model.get("created_at"))
    source_key = f"{model_id}@{to_iso8601(modified)}"
    digest = hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:24]
    tags = string_list(model.get("tags"))
    card_data = model.get("cardData") if isinstance(model.get("cardData"), dict) else {}
    links = sorted(set(extract_urls(model_card))) if model_card else []
    summary = model_summary(model_card, card_data)
    organization = model_id.split("/", 1)[0] if "/" in model_id else None

    return NormalizedItem(
        id=f"huggingface:model:{digest}",
        source="huggingface",
        source_id=source_key,
        kind="model",
        title=model_id,
        url=f"https://huggingface.co/{model_id}",
        discovered_at=to_iso8601(run_at),
        published_at=to_iso8601(created) if created else None,
        updated_at=to_iso8601(modified),
        summary=summary,
        organization=organization,
        topics=classification.topics,
        matched_terms=classification.matched_terms,
        scores={"relevance": classification.relevance},
        metadata={
            "action": action,
            "repo_id": model_id,
            "sha": string_value(model.get("sha")),
            "pipeline_tag": string_value(model.get("pipeline_tag")),
            "library_name": string_value(model.get("library_name")),
            "tags": tags,
            "downloads": numeric_value(model.get("downloads")),
            "likes": numeric_value(model.get("likes")),
            "created_at": to_iso8601(created) if created else None,
            "last_modified": to_iso8601(modified),
            "links": links,
            "classification": classification.evidence,
        },
    )


def model_text(model: dict[str, Any]) -> tuple[str, list[str]]:
    tags = string_list(model.get("tags"))
    fragments = [
        string_value(model.get("pipeline_tag")) or "",
        string_value(model.get("library_name")) or "",
        " ".join(tags),
    ]
    card_data = model.get("cardData")
    if isinstance(card_data, dict):
        fragments.extend(flatten_card_data(card_data))
    return "\n".join(fragment for fragment in fragments if fragment), tags


def flatten_card_data(data: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key, value in data.items():
        if key.casefold() in {"model-index", "model_index"}:
            continue
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, (list, tuple)):
            values.extend(str(item) for item in value if isinstance(item, (str, int, float)))
    return values


def model_summary(model_card: str, card_data: dict[str, Any]) -> str | None:
    description = card_data.get("description")
    if isinstance(description, str) and description.strip():
        return compact_text(description, 1000)
    if not model_card:
        return None
    without_frontmatter = re.sub(
        r"\A---\s*\n.*?\n---\s*\n", "", model_card, count=1, flags=re.DOTALL
    )
    lines = []
    for line in without_frontmatter.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "[", "!", "<")):
            if lines:
                break
            continue
        lines.append(stripped)
        if len(" ".join(lines)) >= 1000:
            break
    return compact_text(" ".join(lines), 1000) if lines else None


def compact_text(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"


def model_last_modified(model: dict[str, Any]) -> datetime | None:
    return parse_hf_datetime(model.get("lastModified") or model.get("last_modified"))


def parse_hf_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return parse_iso8601(value)


def next_link(value: str | None) -> str | None:
    if not value:
        return None
    for part in value.split(","):
        match = _LINK_NEXT_RE.search(part.strip())
        if match:
            return match.group(1)
    return None


def string_value(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def numeric_value(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, (int, float)) else None
