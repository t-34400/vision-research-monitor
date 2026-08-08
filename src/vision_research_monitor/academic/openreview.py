from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from ..models import NormalizedItem, to_iso8601
from .common import AcademicCoverageError, AcademicRunResult, collection_window, initialize_result, normalize_window
from .http import AcademicHttpClient
from .matching import AcademicLexicalMatcher


class OpenReviewCollector:
    def __init__(
        self,
        client: AcademicHttpClient,
        state: dict[str, Any],
        config: dict[str, Any],
        taxonomy: dict[str, Any],
        *,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.state = state
        self.config = config
        self.matcher = AcademicLexicalMatcher(taxonomy, config["matching"])
        self.sleeper = sleeper
        self.monotonic = monotonic
        self._last_request_at: float | None = None

    def collection_window(self, run_at: datetime) -> tuple[datetime, datetime]:
        openreview_state = self.state.setdefault("academic", {}).setdefault("openreview", {})
        return collection_window(
            run_at,
            openreview_state.get("last_successful_at"),
            self.config["window"],
            source_name="OpenReview",
        )

    def collect(
        self,
        run_at: datetime,
        *,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        explicit_backfill: bool = False,
    ) -> AcademicRunResult:
        run_at = run_at.astimezone(timezone.utc)
        if window_start is None or window_end is None:
            window_start, window_end = self.collection_window(run_at)
        window_start, window_end = normalize_window(window_start, window_end)
        result = initialize_result(window_start, window_end)
        state = self.state.setdefault("academic", {}).setdefault("openreview", {})
        editions_state = state.setdefault("editions", {})
        threshold = float(self.config["matching"]["minimum_relevance_score"])

        for edition in self.config["openreview"]["editions"]:
            if not edition.get("enabled", True):
                continue
            venue_id = edition["venue_id"]
            edition_state = editions_state.setdefault(venue_id, {})
            note_state = edition_state.setdefault("notes", {})
            bootstrap = (
                self.config["openreview"]["bootstrap_full_scan"]
                and not edition_state.get("bootstrapped", False)
                and not explicit_backfill
            )
            try:
                notes = self._collect_edition(edition, window_start, window_end, bootstrap=bootstrap)
            except Exception as exc:
                result.add_error(f"openreview:{venue_id}", exc)
                continue

            for note in notes:
                title = string_content(note, "title")
                abstract = string_content(note, "abstract")
                keywords = list_content(note, "keywords")
                match = self.matcher.match(title, abstract, keywords=keywords)
                if match.score < threshold:
                    continue

                item = normalize_openreview_note(note, edition, match.score, match.topics, match.matched_terms, run_at)
                result.items.append(item)
                note_id = str(note["id"])
                current_status = str(item.metadata["status"])
                previous = note_state.get(note_id)
                if isinstance(previous, dict):
                    previous_status = previous.get("status")
                    if isinstance(previous_status, str) and previous_status != current_status:
                        result.items.append(
                            normalize_status_transition(
                                note,
                                edition,
                                previous_status,
                                current_status,
                                match.score,
                                match.topics,
                                match.matched_terms,
                                run_at,
                            )
                        )
                note_state[note_id] = {
                    "status": current_status,
                    "tmdate": integer_value(note.get("tmdate")),
                    "last_seen_at": to_iso8601(run_at),
                }

            if bootstrap:
                edition_state["bootstrapped"] = True
                edition_state["bootstrapped_at"] = to_iso8601(run_at)

        result.items.sort(key=lambda item: (item.published_at or "", item.source_id))
        return result

    def _collect_edition(
        self,
        edition: dict[str, Any],
        start: datetime,
        end: datetime,
        *,
        bootstrap: bool,
    ) -> list[dict[str, Any]]:
        page_size = int(self.config["openreview"]["page_size"])
        max_pages = int(self.config["openreview"]["max_pages_per_edition"])
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        offset = 0
        collected: list[dict[str, Any]] = []

        for _ in range(max_pages):
            params: dict[str, Any] = {
                "content.venueid": edition["venue_id"],
                "limit": page_size,
                "offset": offset,
                "sort": "tcdate:asc" if bootstrap else "tmdate:desc",
            }
            self._pace()
            response = self.client.get_json("/notes", params=params)
            payload = response.data
            notes = payload.get("notes", []) if isinstance(payload, dict) else []
            if not isinstance(notes, list):
                raise AcademicCoverageError(f"OpenReview returned invalid notes payload for {edition['venue_id']}")

            for note in notes:
                if not isinstance(note, dict):
                    continue
                if bootstrap:
                    collected.append(note)
                    continue
                activity = note_activity_ms(note)
                if activity is None or start_ms <= activity <= end_ms:
                    collected.append(note)

            offset += len(notes)
            if len(notes) < page_size:
                return collected
            if not bootstrap and notes:
                oldest_activity = min(
                    (value for note in notes if isinstance(note, dict) and (value := note_activity_ms(note)) is not None),
                    default=None,
                )
                if oldest_activity is not None and oldest_activity < start_ms:
                    return collected

        raise AcademicCoverageError(
            f"OpenReview edition {edition['venue_id']} exceeded {max_pages} pages; refusing to truncate"
        )

    def _pace(self) -> None:
        interval = float(self.config["openreview"]["request_interval_seconds"])
        if self._last_request_at is not None:
            wait = interval - (self.monotonic() - self._last_request_at)
            if wait > 0:
                self.sleeper(wait)
        self._last_request_at = self.monotonic()


def normalize_openreview_note(
    note: dict[str, Any],
    edition: dict[str, Any],
    relevance: float,
    topics: list[str],
    matched_terms: list[str],
    run_at: datetime,
) -> NormalizedItem:
    note_id = str(note["id"])
    status = normalize_status(note)
    authors = list_content(note, "authors")
    author_ids = list_content(note, "authorids")
    keywords = list_content(note, "keywords")
    published_ms = first_integer(note, "odate", "pdate", "tcdate", "cdate")
    updated_ms = first_integer(note, "tmdate", "mdate")
    return NormalizedItem(
        id=f"openreview:paper:{note_id}",
        source="openreview",
        source_id=note_id,
        kind="paper",
        title=string_content(note, "title"),
        url=f"https://openreview.net/forum?id={note_id}",
        discovered_at=to_iso8601(run_at),
        published_at=milliseconds_to_iso(published_ms),
        updated_at=milliseconds_to_iso(updated_ms),
        summary=string_content(note, "abstract") or None,
        authors=authors,
        venue=edition["venue"],
        topics=topics,
        matched_terms=matched_terms,
        scores={"relevance": relevance},
        metadata={
            "status": status,
            "venue_year": edition["year"],
            "openreview_venue_id": edition["venue_id"],
            "venue_label": string_content(note, "venue") or None,
            "number": scalar_content(note, "number"),
            "keywords": keywords,
            "author_ids": author_ids,
            "pdf": scalar_content(note, "pdf"),
            "tcdate": integer_value(note.get("tcdate")),
            "tmdate": integer_value(note.get("tmdate")),
            "pdate": integer_value(note.get("pdate")),
            "odate": integer_value(note.get("odate")),
            "invitations": note.get("invitations", []),
        },
    )


def normalize_status_transition(
    note: dict[str, Any],
    edition: dict[str, Any],
    previous_status: str,
    current_status: str,
    relevance: float,
    topics: list[str],
    matched_terms: list[str],
    run_at: datetime,
) -> NormalizedItem:
    note_id = str(note["id"])
    transition_ms = first_integer(note, "tmdate", "mdate", "pdate", "odate", "tcdate", "cdate")
    transition_key = str(transition_ms) if transition_ms is not None else to_iso8601(run_at)
    source_id = f"{note_id}:status:{previous_status}:{current_status}:{transition_key}"
    title = string_content(note, "title")
    return NormalizedItem(
        id=f"openreview:event:{source_id}",
        source="openreview",
        source_id=source_id,
        kind="event",
        title=title,
        url=f"https://openreview.net/forum?id={note_id}",
        discovered_at=to_iso8601(run_at),
        published_at=milliseconds_to_iso(transition_ms) or to_iso8601(run_at),
        updated_at=milliseconds_to_iso(transition_ms),
        summary=string_content(note, "abstract") or None,
        authors=list_content(note, "authors"),
        venue=edition["venue"],
        topics=topics,
        matched_terms=matched_terms,
        scores={"relevance": relevance},
        metadata={
            "action": "status_changed",
            "paper_id": note_id,
            "paper_url": f"https://openreview.net/forum?id={note_id}",
            "previous_status": previous_status,
            "status": current_status,
            "venue_year": edition["year"],
            "openreview_venue_id": edition["venue_id"],
            "tmdate": integer_value(note.get("tmdate")),
            "pdate": integer_value(note.get("pdate")),
        },
    )


def normalize_status(note: dict[str, Any]) -> str:
    venue_label = string_content(note, "venue").casefold()
    if "withdraw" in venue_label:
        return "withdrawn"
    if "desk reject" in venue_label or "rejected" in venue_label or "reject" in venue_label:
        return "rejected"
    if integer_value(note.get("pdate")) is not None:
        return "accepted"
    return "submitted"


def note_activity_ms(note: dict[str, Any]) -> int | None:
    return first_integer(note, "tmdate", "tcdate", "mdate", "cdate")


def content_value(note: dict[str, Any], key: str) -> Any:
    content = note.get("content")
    if not isinstance(content, dict):
        return None
    value = content.get(key)
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def scalar_content(note: dict[str, Any], key: str) -> Any:
    value = content_value(note, key)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return None


def string_content(note: dict[str, Any], key: str) -> str:
    value = content_value(note, key)
    return " ".join(value.split()) if isinstance(value, str) else ""


def list_content(note: dict[str, Any], key: str) -> list[str]:
    value = content_value(note, key)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def first_integer(note: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = integer_value(note.get(key))
        if value is not None:
            return value
    return None


def integer_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def milliseconds_to_iso(value: int | None) -> str | None:
    if value is None:
        return None
    return to_iso8601(datetime.fromtimestamp(value / 1000, tz=timezone.utc))
