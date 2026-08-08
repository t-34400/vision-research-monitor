import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from vision_research_monitor.academic.http import AcademicHttpClient
from vision_research_monitor.academic.openreview import OpenReviewCollector, normalize_status


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/academic"


def load_inputs() -> tuple[dict, dict]:
    config = yaml.safe_load((ROOT / "config/academic.yaml").read_text())
    config["openreview"]["editions"] = [config["openreview"]["editions"][0]]
    taxonomy = yaml.safe_load((ROOT / "config/taxonomy.yaml").read_text())
    return config, taxonomy


def test_openreview_bootstrap_filters_and_normalizes_notes() -> None:
    config, taxonomy = load_inputs()
    payload = json.loads((FIXTURES / "openreview_notes.json").read_text())
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    state: dict = {}
    with AcademicHttpClient(
        config["openreview"]["base_url"],
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    ) as client:
        collector = OpenReviewCollector(
            client,
            state,
            config,
            taxonomy,
            sleeper=lambda _: None,
            monotonic=lambda: 0.0,
        )
        result = collector.collect(datetime(2026, 8, 8, tzinfo=timezone.utc))

    assert result.failed_targets == 0
    assert len(result.items) == 1
    item = result.items[0]
    assert item.id == "openreview:paper:note-gaussian"
    assert item.venue == "cvpr"
    assert item.metadata["status"] == "accepted"
    assert "pose_free_3d_reconstruction" in item.topics
    assert "mintcdate" not in requests[0].url.params
    edition_state = state["academic"]["openreview"]["editions"]["thecvf.com/CVPR/2026/Conference"]
    assert edition_state["bootstrapped"] is True


def test_openreview_incremental_collection_uses_creation_checkpoint() -> None:
    config, taxonomy = load_inputs()
    payload = json.loads((FIXTURES / "openreview_notes.json").read_text())
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    state = {
        "academic": {
            "openreview": {
                "last_successful_at": "2026-08-07T00:00:00Z",
                "editions": {"thecvf.com/CVPR/2026/Conference": {"bootstrapped": True}},
            }
        }
    }
    with AcademicHttpClient(
        config["openreview"]["base_url"],
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    ) as client:
        collector = OpenReviewCollector(
            client,
            state,
            config,
            taxonomy,
            sleeper=lambda _: None,
            monotonic=lambda: 0.0,
        )
        collector.collect(datetime(2026, 8, 8, tzinfo=timezone.utc))

    assert "mintcdate" in requests[0].url.params


def test_openreview_status_normalization() -> None:
    assert normalize_status({"content": {"venue": {"value": "Withdrawn Submission"}}}) == "withdrawn"
    assert normalize_status({"content": {"venue": {"value": "Rejected"}}}) == "rejected"
    assert normalize_status({"pdate": 1, "content": {"venue": {"value": "CVPR 2026"}}}) == "accepted"
    assert normalize_status({"content": {"venue": {"value": "CVPR 2026 Submission"}}}) == "submitted"
