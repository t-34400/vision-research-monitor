import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vision_research_monitor.github.client import ApiResult
from vision_research_monitor.github.watch import GitHubWatchCollector, repository_popularity

FIXTURES = Path(__file__).parent / "fixtures/github"


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeGitHubClient:
    def __init__(self, repository: dict[str, Any]) -> None:
        self.repository = repository
        self.account_repositories = [copy.deepcopy(repository)]
        self.releases: list[dict[str, Any]] = []
        self.tags: list[dict[str, Any]] = []
        self.commit: dict[str, Any] | None = fixture("commit.json")
        self.calls: list[tuple[str, dict[str, Any] | None, bool]] = []

    def get_json(
        self, path: str, *, params: dict[str, Any] | None = None, conditional: bool = False
    ) -> ApiResult:
        self.calls.append((path, copy.deepcopy(params), conditional))
        if path.startswith("/orgs/") or path.startswith("/users/"):
            page = int((params or {}).get("page", 1))
            records = self.account_repositories if page == 1 else []
            return ApiResult(copy.deepcopy(records), 200, {})
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


def watchlist(*, repositories: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "account_discovery": {"overlap_minutes": 120, "max_pages_per_run": 5},
        "accounts": [
            {
                "login": "example",
                "type": "organization",
                "priority": "high",
                "topic_filter_required": False,
            }
        ],
        "repositories": repositories or [],
    }


def explicit_watchlist() -> dict[str, Any]:
    return watchlist(
        repositories=[
            {
                "repo": "example/vision-project",
                "priority": "high",
                "topics": ["gaussian_splatting"],
            }
        ]
    )


def empty_state() -> dict[str, Any]:
    return {"version": 1, "accounts": {}, "repositories": {}, "http_cache": {}}


def test_first_account_run_establishes_timestamp_baseline_without_inventory() -> None:
    client = FakeGitHubClient(fixture("repository.json"))
    state = empty_state()
    collector = GitHubWatchCollector(client, state, watchlist())

    result = collector.collect(datetime(2026, 8, 8, 0, 0, tzinfo=UTC))

    assert result.items == []
    account_state = state["accounts"]["organization:example"]
    assert account_state["last_checked_at"] == "2026-08-08T00:00:00Z"
    assert "repository_ids" not in account_state
    assert state["repositories"] == {}
    path, params, _ = client.calls[0]
    assert path == "/orgs/example/repos"
    assert params == {
        "type": "public",
        "sort": "created",
        "direction": "desc",
        "per_page": 100,
        "page": 1,
    }


def test_account_run_emits_only_repositories_created_after_checkpoint() -> None:
    repository = fixture("repository.json")
    repository["created_at"] = "2026-08-07T12:00:00Z"
    client = FakeGitHubClient(repository)
    state = empty_state()
    collector = GitHubWatchCollector(client, state, watchlist())
    collector.collect(datetime(2026, 8, 8, 0, 0, tzinfo=UTC))

    new_repository = copy.deepcopy(repository)
    new_repository["id"] = 202
    new_repository["name"] = "new-tool"
    new_repository["full_name"] = "example/new-tool"
    new_repository["html_url"] = "https://github.com/example/new-tool"
    new_repository["created_at"] = "2026-08-08T01:00:00Z"
    client.account_repositories = [new_repository, repository]

    result = collector.collect(datetime(2026, 8, 8, 2, 0, tzinfo=UTC))

    assert [item.id for item in result.items] == ["github:repository:202"]
    assert state["repositories"] == {}
    assert state["accounts"]["organization:example"]["last_checked_at"] == "2026-08-08T02:00:00Z"


def test_explicit_repository_emits_metadata_release_and_head_activity() -> None:
    repository = fixture("repository.json")
    client = FakeGitHubClient(repository)
    state = empty_state()
    collector = GitHubWatchCollector(client, state, explicit_watchlist())
    collector.collect(datetime(2026, 8, 8, 0, 0, tzinfo=UTC))

    repository["description"] = "Updated Gaussian splatting project"
    repository["updated_at"] = "2026-08-08T01:15:00Z"
    repository["pushed_at"] = "2026-08-08T01:10:00Z"
    client.repository = repository
    client.releases = [fixture("release.json")]
    client.tags = [fixture("tag.json")]
    changed_commit = fixture("commit.json")
    changed_commit["sha"] = "new-head"
    changed_commit["commit"]["committer"]["date"] = "2026-08-08T01:10:00Z"
    client.commit = changed_commit

    result = collector.collect(datetime(2026, 8, 8, 2, 0, tzinfo=UTC))
    kinds = [item.kind for item in result.items]

    assert kinds.count("event") == 1
    assert kinds.count("release") == 1
    assert kinds.count("commit") == 1
    assert kinds.count("tag") == 1


def test_subsequent_tag_is_emitted_after_tag_baseline_exists() -> None:
    repository = fixture("repository.json")
    client = FakeGitHubClient(repository)
    client.tags = [fixture("tag.json")]
    state = empty_state()
    collector = GitHubWatchCollector(client, state, explicit_watchlist())
    collector.collect(datetime(2026, 8, 8, 0, 0, tzinfo=UTC))

    new_tag = fixture("tag.json")
    new_tag["name"] = "v1.2.0"
    client.tags = [new_tag, fixture("tag.json")]
    result = collector.collect(datetime(2026, 8, 8, 4, 0, tzinfo=UTC))

    assert [item.kind for item in result.items].count("tag") == 1
    assert any(item.metadata.get("tag_name") == "v1.2.0" for item in result.items)


def test_auto_watch_registry_adds_normal_priority_repository_target() -> None:
    repository = fixture("repository.json")
    client = FakeGitHubClient(repository)
    state = empty_state()
    registry = {
        "version": 1,
        "repositories": {
            "101": {
                "repo_id": "101",
                "full_name": "example/vision-project",
                "topics": ["gaussian_splatting"],
                "priority": "normal",
            }
        },
    }

    collector = GitHubWatchCollector(client, state, watchlist(), registry)
    collector.collect(datetime(2026, 8, 8, 0, 0, tzinfo=UTC))

    assert [target["repo"] for target in collector.repository_targets] == ["example/vision-project"]
    assert state["repositories"]["101"]["configured_names"] == ["example/vision-project"]


def test_legacy_account_inventory_state_is_pruned_to_current_detail_targets() -> None:
    repository = fixture("repository.json")
    client = FakeGitHubClient(repository)
    state = empty_state()
    state["repositories"] = {
        "101": {
            "snapshot": {
                "id": 101,
                "full_name": "example/vision-project",
                "html_url": "https://github.com/example/vision-project",
            },
            "configured_names": ["example/vision-project"],
            "details": {},
        },
        "999": {
            "snapshot": {
                "id": 999,
                "full_name": "example/legacy-inventory-only",
                "html_url": "https://github.com/example/legacy-inventory-only",
            },
            "details": {},
        },
    }

    GitHubWatchCollector(client, state, explicit_watchlist())

    assert set(state["repositories"]) == {"101"}


def test_repository_popularity_uses_previous_snapshot() -> None:
    repository = fixture("repository.json")
    repository["stargazers_count"] = 145
    repository["forks_count"] = 12

    popularity = repository_popularity(repository, {"stars": 120})

    assert popularity == {"stars": 145, "forks": 12, "stars_delta": 25}
