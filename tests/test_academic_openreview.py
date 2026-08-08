import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from vision_research_monitor.academic.openreview import OpenReviewCollector, normalize_status
from vision_research_monitor.academic.openreview_client import note_to_mapping

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/academic"


class FakeNote:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def to_json(self) -> dict[str, Any]:
        return dict(self.payload)


class FakeOpenReviewClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.notes = [FakeNote(note) for note in payload["notes"]]
        self.calls: list[dict[str, Any]] = []

    def get_notes(
        self,
        *,
        content: dict[str, Any] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        sort: str | None = None,
    ) -> list[Any]:
        self.calls.append({"content": content, "limit": limit, "offset": offset, "sort": sort})
        start = offset or 0
        end = start + (limit or len(self.notes))
        return self.notes[start:end]


def load_inputs() -> tuple[dict, dict]:
    config = yaml.safe_load((ROOT / "config/academic.yaml").read_text())
    config["openreview"]["editions"] = [config["openreview"]["editions"][0]]
    taxonomy = yaml.safe_load((ROOT / "config/taxonomy.yaml").read_text())
    return config, taxonomy


def test_openreview_client_note_adapter_accepts_official_like_objects() -> None:
    payload = {"id": "note-1", "content": {"title": {"value": "Example"}}, "tmdate": 123}
    assert note_to_mapping(FakeNote(payload)) == payload


def test_openreview_bootstrap_filters_and_normalizes_notes() -> None:
    config, taxonomy = load_inputs()
    payload = json.loads((FIXTURES / "openreview_notes.json").read_text())
    client = FakeOpenReviewClient(payload)
    state: dict = {}

    collector = OpenReviewCollector(
        client,
        state,
        config,
        taxonomy,
        sleeper=lambda _: None,
        monotonic=lambda: 0.0,
    )
    result = collector.collect(datetime(2026, 8, 8, tzinfo=UTC))

    assert result.failed_targets == 0
    assert len(result.items) == 1
    item = result.items[0]
    assert item.id == "openreview:paper:note-gaussian"
    assert item.venue == "cvpr"
    assert item.metadata["status"] == "accepted"
    assert "pose_free_3d_reconstruction" in item.topics
    assert client.calls[0] == {
        "content": {"venueid": "thecvf.com/CVPR/2026/Conference"},
        "limit": 1000,
        "offset": 0,
        "sort": "tcdate:asc",
    }
    edition_state = state["academic"]["openreview"]["editions"]["thecvf.com/CVPR/2026/Conference"]
    assert edition_state["bootstrapped"] is True


def test_openreview_incremental_collection_uses_modification_order() -> None:
    config, taxonomy = load_inputs()
    payload = json.loads((FIXTURES / "openreview_notes.json").read_text())
    client = FakeOpenReviewClient(payload)
    state = {
        "academic": {
            "openreview": {
                "last_successful_at": "2026-08-07T00:00:00Z",
                "editions": {"thecvf.com/CVPR/2026/Conference": {"bootstrapped": True}},
            }
        }
    }

    collector = OpenReviewCollector(
        client,
        state,
        config,
        taxonomy,
        sleeper=lambda _: None,
        monotonic=lambda: 0.0,
    )
    collector.collect(datetime(2026, 8, 8, tzinfo=UTC))

    assert client.calls[0]["sort"] == "tmdate:desc"
    assert client.calls[0]["content"] == {"venueid": "thecvf.com/CVPR/2026/Conference"}


def test_openreview_status_normalization() -> None:
    assert (
        normalize_status({"content": {"venue": {"value": "Withdrawn Submission"}}}) == "withdrawn"
    )
    assert normalize_status({"content": {"venue": {"value": "Rejected"}}}) == "rejected"
    assert (
        normalize_status({"pdate": 1, "content": {"venue": {"value": "CVPR 2026"}}}) == "accepted"
    )
    assert (
        normalize_status({"content": {"venue": {"value": "CVPR 2026 Submission"}}}) == "submitted"
    )


def test_openreview_emits_status_transition_for_modified_note() -> None:
    config, taxonomy = load_inputs()
    payload = json.loads((FIXTURES / "openreview_notes.json").read_text())
    client = FakeOpenReviewClient(payload)
    state = {
        "academic": {
            "openreview": {
                "last_successful_at": "2026-08-07T12:00:00Z",
                "editions": {
                    "thecvf.com/CVPR/2026/Conference": {
                        "bootstrapped": True,
                        "notes": {
                            "note-gaussian": {
                                "status": "submitted",
                                "tmdate": 1786032000000,
                                "last_seen_at": "2026-08-06T16:00:00Z",
                            }
                        },
                    }
                },
            }
        }
    }

    result = OpenReviewCollector(
        client,
        state,
        config,
        taxonomy,
        sleeper=lambda _: None,
        monotonic=lambda: 0.0,
    ).collect(datetime(2026, 8, 8, tzinfo=UTC))

    transition = next(item for item in result.items if item.kind == "event")
    assert transition.metadata["action"] == "status_changed"
    assert transition.metadata["previous_status"] == "submitted"
    assert transition.metadata["status"] == "accepted"
    assert transition.metadata["paper_id"] == "note-gaussian"
    assert (
        state["academic"]["openreview"]["editions"]["thecvf.com/CVPR/2026/Conference"]["notes"][
            "note-gaussian"
        ]["status"]
        == "accepted"
    )
