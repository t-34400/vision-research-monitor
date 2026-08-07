from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml

from vision_research_monitor.github.client import GitHubClient
from vision_research_monitor.github.discovery import DiscoveryCoverageError, GitHubDiscoveryCollector


ROOT = Path(__file__).resolve().parents[1]


def load_fixture_config() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    config = yaml.safe_load((ROOT / "config/github_discovery.yaml").read_text(encoding="utf-8"))
    taxonomy = yaml.safe_load((ROOT / "config/taxonomy.yaml").read_text(encoding="utf-8"))
    venues = yaml.safe_load((ROOT / "config/venues.yaml").read_text(encoding="utf-8"))
    return config, taxonomy, venues


def repository(repo_id: int = 101, description: str = "Feed-forward 3D reconstruction with Gaussian splatting") -> dict[str, Any]:
    return {
        "id": repo_id,
        "name": "fast-3d",
        "full_name": "research/fast-3d",
        "html_url": "https://github.com/research/fast-3d",
        "description": description,
        "owner": {"login": "research"},
        "created_at": "2026-08-08T00:00:00Z",
        "updated_at": "2026-08-08T01:00:00Z",
        "pushed_at": "2026-08-08T01:00:00Z",
        "topics": ["3d-reconstruction", "gaussian-splatting"],
        "stargazers_count": 42,
        "forks_count": 3,
        "language": "Python",
        "fork": False,
        "archived": False,
    }


def test_topic_discovery_aggregates_created_and_pushed_hits() -> None:
    config, taxonomy, venues = load_fixture_config()
    config = deepcopy(config)
    config["search"]["request_interval_seconds"] = 0
    config["query_families"] = [
        {
            "id": "neural_rendering",
            "queries": [
                {"id": "gaussian_splatting", "text": '"gaussian splatting"', "topics": ["gaussian_splatting"]}
            ],
        }
    ]
    config["venue_search"]["enabled"] = False
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"total_count": 1, "incomplete_results": False, "items": [repository()]})

    state = {"version": 1, "http_cache": {}}
    run_at = datetime(2026, 8, 8, 2, tzinfo=timezone.utc)
    with GitHubClient(None, state["http_cache"], transport=httpx.MockTransport(handler)) as client:
        result = GitHubDiscoveryCollector(client, state, config, taxonomy, venues).collect(
            run_at,
            window_start=run_at - timedelta(hours=12),
            window_end=run_at,
        )

    assert result.failed_queries == 0
    assert len(result.items) == 1
    item = result.items[0]
    assert item.id == "github:repository:101"
    assert "gaussian_splatting" in item.topics
    assert item.metadata["discovery_modes"] == ["created", "pushed"]
    assert item.scores["relevance"] >= 0.35
    queries = [request.url.params["q"] for request in requests]
    assert any("created:" in query for query in queries)
    assert any("pushed:" in query and "stars:>=10" in query for query in queries)


def test_dense_search_window_is_split_before_pagination_limit() -> None:
    config, taxonomy, venues = load_fixture_config()
    config = deepcopy(config)
    config["search"]["request_interval_seconds"] = 0
    config["search"]["max_pages_per_slice"] = 1
    config["query_families"] = [
        {
            "id": "depth",
            "queries": [
                {"id": "metric_depth", "text": '"metric depth"', "topics": ["metric_depth"], "modes": ["created"]}
            ],
        }
    ]
    config["venue_search"]["enabled"] = False
    original_range_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal original_range_calls
        query = request.url.params["q"]
        if "2026-08-08T00:00:00+00:00..2026-08-08T02:00:00+00:00" in query:
            original_range_calls += 1
            return httpx.Response(200, json={"total_count": 101, "incomplete_results": False, "items": []})
        repo_id = 201 if "T01:00:00+00:00" in query.split("..", 1)[1] else 202
        return httpx.Response(200, json={"total_count": 1, "incomplete_results": False, "items": [repository(repo_id, "metric depth estimation")]})

    state = {"version": 1, "http_cache": {}}
    start = datetime(2026, 8, 8, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 8, 2, tzinfo=timezone.utc)
    with GitHubClient(None, state["http_cache"], transport=httpx.MockTransport(handler)) as client:
        result = GitHubDiscoveryCollector(client, state, config, taxonomy, venues).collect(
            end,
            window_start=start,
            window_end=end,
        )

    assert original_range_calls == 1
    assert {item.id for item in result.items} == {"github:repository:201", "github:repository:202"}


def test_venue_only_candidate_uses_readme_for_topic_gate() -> None:
    config, taxonomy, venues = load_fixture_config()
    config = deepcopy(config)
    config["search"]["request_interval_seconds"] = 0
    config["query_families"] = []
    config["venue_search"] = {
        "enabled": True,
        "priorities": ["core"],
        "venue_ids": ["cvpr"],
        "year_offsets": [0],
        "modes": ["created"],
    }
    candidate = repository(301, "Official implementation")
    candidate["topics"] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/readme"):
            return httpx.Response(200, text="CVPR 2026 project for monocular depth estimation from a single image")
        return httpx.Response(200, json={"total_count": 1, "incomplete_results": False, "items": [candidate]})

    state = {"version": 1, "http_cache": {}}
    run_at = datetime(2026, 8, 8, 2, tzinfo=timezone.utc)
    with GitHubClient(None, state["http_cache"], transport=httpx.MockTransport(handler)) as client:
        result = GitHubDiscoveryCollector(client, state, config, taxonomy, venues).collect(
            run_at,
            window_start=run_at - timedelta(hours=12),
            window_end=run_at,
        )

    assert len(result.items) == 1
    assert "monocular_depth" in result.items[0].topics
    assert result.items[0].metadata["venue_hits"][0]["venue"] == "cvpr"


def test_stale_checkpoint_requires_explicit_backfill() -> None:
    config, taxonomy, venues = load_fixture_config()
    state = {
        "version": 1,
        "http_cache": {},
        "last_successful_at": "2026-08-01T00:00:00Z",
    }
    run_at = datetime(2026, 8, 8, 0, tzinfo=timezone.utc)
    with GitHubClient(None, state["http_cache"], transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client:
        collector = GitHubDiscoveryCollector(client, state, config, taxonomy, venues)
        try:
            collector.collection_window(run_at)
        except DiscoveryCoverageError as exc:
            assert "maximum automatic catch-up" in str(exc)
        else:
            raise AssertionError("expected stale checkpoint to require backfill")
