from __future__ import annotations

from typing import Any, Protocol


class OpenReviewNotesClient(Protocol):
    def get_notes(
        self,
        *,
        content: dict[str, Any] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        sort: str | None = None,
    ) -> list[Any]: ...


def note_to_mapping(note: Any) -> dict[str, Any]:
    if isinstance(note, dict):
        return dict(note)

    to_json = getattr(note, "to_json", None)
    if callable(to_json):
        payload = to_json()
        if isinstance(payload, dict):
            return payload

    fields = (
        "id",
        "forum",
        "replyto",
        "content",
        "invitations",
        "readers",
        "writers",
        "signatures",
        "number",
        "cdate",
        "mdate",
        "ddate",
        "tcdate",
        "tmdate",
        "pdate",
        "odate",
        "license",
    )
    payload = {field: getattr(note, field) for field in fields if hasattr(note, field)}
    if "id" not in payload:
        raise TypeError(f"Unsupported OpenReview note object: {type(note).__name__}")
    return payload
