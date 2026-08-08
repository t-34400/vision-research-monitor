from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from vision_research_monitor.http import HttpClient
from vision_research_monitor.sources.huggingface import HuggingFaceCollector, next_link

ROOT = Path(__file__).resolve().parents[1]


def load_inputs() -> tuple[dict, dict]:
    config = yaml.safe_load((ROOT / "config/sources.yaml").read_text())
    config["huggingface"]["queries"] = [{"id": "depth", "text": "depth estimation"}]
    taxonomy = yaml.safe_load((ROOT / "config/taxonomy.yaml").read_text())
    return config, taxonomy


def test_huggingface_collector_emits_recent_relevant_model() -> None:
    config, taxonomy = load_inputs()
    payload = [
        {
            "id": "example/metric-depth-model",
            "lastModified": "2026-08-08T05:00:00.000Z",
            "createdAt": "2026-08-08T02:00:00.000Z",
            "sha": "abc123",
            "pipeline_tag": "depth-estimation",
            "tags": ["monocular depth", "metric depth"],
            "downloads": 42,
            "likes": 3,
        },
        {
            "id": "example/database-model",
            "lastModified": "2026-08-08T04:00:00.000Z",
            "createdAt": "2026-08-08T03:00:00.000Z",
            "tags": ["database"],
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/models":
            return httpx.Response(200, json=payload)
        return httpx.Response(200, text="A model card about relational database optimization.")

    state: dict = {}
    with HttpClient(
        config["huggingface"]["base_url"],
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    ) as client:
        result = HuggingFaceCollector(
            client,
            state,
            config,
            taxonomy,
            sleeper=lambda _: None,
            monotonic=lambda: 0.0,
        ).collect(
            datetime(2026, 8, 8, 8, tzinfo=timezone.utc),
            window_start=datetime(2026, 8, 8, 0, tzinfo=timezone.utc),
            window_end=datetime(2026, 8, 8, 8, tzinfo=timezone.utc),
        )

    assert result.failed_targets == 0
    assert len(result.items) == 1
    item = result.items[0]
    assert item.kind == "model"
    assert item.metadata["action"] == "discovered"
    assert {"monocular_depth", "metric_depth"}.issubset(item.topics)
    assert state["sources"]["huggingface"]["repositories"]["example/metric-depth-model"]["last_modified"] == "2026-08-08T05:00:00Z"


def test_huggingface_overlap_does_not_reemit_same_revision() -> None:
    config, taxonomy = load_inputs()
    payload = [{
        "id": "example/metric-depth-model",
        "lastModified": "2026-08-08T05:00:00Z",
        "createdAt": "2026-08-08T02:00:00Z",
        "tags": ["metric depth"],
    }]
    state = {
        "sources": {
            "huggingface": {
                "repositories": {
                    "example/metric-depth-model": {
                        "last_modified": "2026-08-08T05:00:00Z",
                        "last_seen_at": "2026-08-08T05:10:00Z",
                    }
                }
            }
        }
    }
    with HttpClient(
        config["huggingface"]["base_url"],
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
        sleeper=lambda _: None,
    ) as client:
        result = HuggingFaceCollector(
            client,
            state,
            config,
            taxonomy,
            sleeper=lambda _: None,
            monotonic=lambda: 0.0,
        ).collect(
            datetime(2026, 8, 8, 8, tzinfo=timezone.utc),
            window_start=datetime(2026, 8, 8, 0, tzinfo=timezone.utc),
            window_end=datetime(2026, 8, 8, 8, tzinfo=timezone.utc),
        )
    assert result.items == []


def test_huggingface_link_header_parser() -> None:
    value = '<https://huggingface.co/api/models?cursor=abc>; rel="next", <https://huggingface.co/api/models?cursor=prev>; rel="prev"'
    assert next_link(value) == "https://huggingface.co/api/models?cursor=abc"
