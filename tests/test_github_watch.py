import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vision_research_monitor.github.client import ApiResult
from vision_research_monitor.github.watch import GitHubWatchCollector


FIXTURES = Path(__file__).parent / "fixtures/github"


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeGitHubClient:
    def __init__(self, repository: dict[str, Any]) -> None:
        self.repository = repository
        self.releases: list[dict[str, Any]] = []
        self.tags: list[dict[str, Any]] = []
        self.commit: dict[str, Any] | None = None

    def get_paginated(self, path: str, *, params: dict[str, Any], max_pages: int = 100) -> list[dict[str, Any]]:
        return [copy.deepcopy(self.repository)]

    def get_json(self, path: str, *, params: dict[str, Any] | None = None, conditional: bool = False) -> ApiResult:
        if path.endswith("/releases"):
            return ApiResult(copy.deepcopy(self.releases), 200, {})
        if path.endswith("/tags"):
            return ApiResult(copy.deepcopy(self.tags), 200, {})
        if "/commits/" in path:
            return ApiResult(copy.deepcopy(self.commit), 200, {})
        return ApiResult(copy.deepcopy(self.repository), 200, {})

    def commit_cache(self, result: ApiResult) -> None:
        return None

    def invalidate_cache(self, result: ApiResult) -> None:
        return None


def watchlist() -> dict[str, Any]:
    return {
        "accounts": [
            {
                "login": "example",
                "type": "organization",
                "priority": "high",
                "topic_filter_required": False,
            }
        ],
        "repositories": [],
    }


def empty_state() -> dict[str, Any]:
    return {"version": 1, "accounts": {}, "repositories": {}, "http_cache": {}}


def test_first_account_run_establishes_baseline_without_historical_items() -> None:
    client = FakeGitHubClient(fixture("repository.json"))
    state = empty_state()
    collector = GitHubWatchCollector(client, state, watchlist())

    result = collector.collect(datetime(2026, 8, 8, 0, 0, tzinfo=timezone.utc))

    assert result.items == []
    assert state["accounts"]["organization:example"]["repository_ids"] == ["101"]
    assert state["repositories"]["101"]["snapshot"]["full_name"] == "example/vision-project"


def test_changed_account_repository_emits_metadata_release_and_head_activity() -> None:
    repository = fixture("repository.json")
    client = FakeGitHubClient(repository)
    state = empty_state()
    collector = GitHubWatchCollector(client, state, watchlist())
    collector.collect(datetime(2026, 8, 8, 0, 0, tzinfo=timezone.utc))

    repository["description"] = "Updated Gaussian splatting project"
    repository["updated_at"] = "2026-08-08T01:15:00Z"
    repository["pushed_at"] = "2026-08-08T01:10:00Z"
    client.releases = [fixture("release.json")]
    client.tags = [fixture("tag.json")]
    client.commit = fixture("commit.json")

    result = collector.collect(datetime(2026, 8, 8, 2, 0, tzinfo=timezone.utc))
    kinds = [item.kind for item in result.items]

    assert kinds.count("event") == 1
    assert kinds.count("release") == 1
    assert kinds.count("commit") == 1
    assert "tag" not in kinds


def test_subsequent_tag_is_emitted_after_tag_baseline_exists() -> None:
    repository = fixture("repository.json")
    client = FakeGitHubClient(repository)
    state = empty_state()
    collector = GitHubWatchCollector(client, state, watchlist())
    collector.collect(datetime(2026, 8, 8, 0, 0, tzinfo=timezone.utc))

    repository["updated_at"] = "2026-08-08T01:00:00Z"
    client.tags = [fixture("tag.json")]
    client.commit = fixture("commit.json")
    collector.collect(datetime(2026, 8, 8, 2, 0, tzinfo=timezone.utc))

    new_tag = fixture("tag.json")
    new_tag["name"] = "v1.2.0"
    repository["updated_at"] = "2026-08-08T03:00:00Z"
    client.tags = [new_tag, fixture("tag.json")]
    result = collector.collect(datetime(2026, 8, 8, 4, 0, tzinfo=timezone.utc))

    assert [item.kind for item in result.items].count("tag") == 1
    assert any(item.metadata.get("tag_name") == "v1.2.0" for item in result.items)
