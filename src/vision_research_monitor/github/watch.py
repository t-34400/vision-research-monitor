from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..models import NormalizedItem, parse_iso8601, to_iso8601
from .client import ApiResult, GitHubApiError, GitHubClient, GitHubNotFoundError

MEANINGFUL_REPOSITORY_FIELDS = (
    "full_name",
    "description",
    "homepage",
    "topics",
    "archived",
    "disabled",
    "fork",
    "visibility",
    "default_branch",
)


@dataclass(slots=True)
class WatchRunResult:
    items: list[NormalizedItem] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    failed_targets: int = 0

    def add_error(self, target: str, exc: Exception) -> None:
        self.failed_targets += 1
        self.diagnostics.append({"level": "error", "target": target, "message": str(exc)})


class GitHubWatchCollector:
    def __init__(
        self, client: GitHubClient, state: dict[str, Any], watchlist: dict[str, Any]
    ) -> None:
        self.client = client
        self.state = state
        self.watchlist = watchlist
        self.state.setdefault("accounts", {})
        self.state.setdefault("repositories", {})

    def collect(self, run_at: datetime) -> WatchRunResult:
        run_at = run_at.astimezone(UTC)
        result = WatchRunResult()

        for account in self.watchlist["accounts"]:
            if not account.get("enabled", True):
                continue
            target = f"{account['type']}:{account['login']}"
            try:
                self._collect_account(account, run_at, result)
            except Exception as exc:
                result.add_error(target, exc)

        for configured in self.watchlist["repositories"]:
            if not configured.get("enabled", True):
                continue
            target = f"repository:{configured['repo']}"
            try:
                self._collect_direct_repository(configured, run_at, result)
            except Exception as exc:
                result.add_error(target, exc)

        self.state["last_run_completed_at"] = to_iso8601(run_at)
        return result

    def _collect_account(
        self, account: dict[str, Any], run_at: datetime, result: WatchRunResult
    ) -> None:
        login = account["login"]
        account_type = account["type"]
        key = f"{account_type}:{login.lower()}"
        previous = self.state["accounts"].get(key)
        repositories = self._list_account_repositories(login, account_type)
        current_ids = {str(repo["id"]) for repo in repositories if "id" in repo}

        if previous is None:
            for repo in repositories:
                self._ensure_repository_state(repo, run_at)
            self.state["accounts"][key] = {
                "login": login,
                "type": account_type,
                "repository_ids": sorted(current_ids),
                "initialized_at": to_iso8601(run_at),
                "last_checked_at": to_iso8601(run_at),
            }
            return

        previous_ids = set(previous.get("repository_ids", []))
        previous_checked = parse_iso8601(previous.get("last_checked_at")) or run_at
        for repo in repositories:
            repo_id = str(repo["id"])
            repo_state = self.state["repositories"].get(repo_id)
            if repo_state is None:
                repo_state = self._ensure_repository_state(repo, run_at)
                popularity = repository_popularity(repo, None)
                result.items.append(
                    self._repository_created_item(repo, account, run_at, popularity)
                )
                self._collect_repository_details(
                    repo,
                    repo_state,
                    account,
                    run_at,
                    result,
                    initial_since=previous_checked,
                    popularity=popularity,
                )
                continue

            old_snapshot = repo_state["snapshot"]
            new_snapshot = repository_snapshot(repo)
            popularity = repository_popularity(repo, old_snapshot)
            changed = meaningful_changes(old_snapshot, new_snapshot)
            activity_changed = old_snapshot.get("updated_at") != new_snapshot.get(
                "updated_at"
            ) or old_snapshot.get("pushed_at") != new_snapshot.get("pushed_at")
            repo_state["snapshot"] = new_snapshot
            repo_state["last_seen_at"] = to_iso8601(run_at)
            if changed:
                result.items.append(
                    self._repository_updated_item(repo, account, changed, run_at, popularity)
                )
            if activity_changed:
                self._collect_repository_details(
                    repo,
                    repo_state,
                    account,
                    run_at,
                    result,
                    initial_since=parse_iso8601(repo_state.get("first_observed_at"))
                    or previous_checked,
                    popularity=popularity,
                )

        for missing_id in sorted(previous_ids - current_ids):
            repo_state = self.state["repositories"].get(missing_id)
            if repo_state is None:
                continue
            result.items.append(
                self._repository_missing_item(
                    repo_state["snapshot"],
                    account,
                    previous.get("last_checked_at", to_iso8601(previous_checked)),
                    run_at,
                )
            )

        previous.update(
            {
                "repository_ids": sorted(current_ids),
                "last_checked_at": to_iso8601(run_at),
            }
        )

    def _collect_direct_repository(
        self,
        configured: dict[str, Any],
        run_at: datetime,
        result: WatchRunResult,
    ) -> None:
        owner, name = configured["repo"].split("/", 1)
        path = f"/repos/{owner}/{name}"
        api_result = self.client.get_json(path, conditional=True)
        if api_result.not_modified:
            repo_state = self._repository_state_for_configured_name(configured["repo"])
            if repo_state is not None:
                self._collect_repository_details_from_state(repo_state, configured, run_at, result)
            return

        repo = require_object(api_result, path)
        repo_id = str(repo["id"])
        repo_state = self.state["repositories"].get(repo_id)
        if repo_state is None:
            repo_state = self._ensure_repository_state(repo, run_at)
            repo_state.setdefault("configured_names", []).append(configured["repo"])
            self.client.commit_cache(api_result)
            self._collect_repository_details(
                repo,
                repo_state,
                configured,
                run_at,
                result,
                initial_since=None,
                popularity=repository_popularity(repo, None),
            )
            return

        configured_names = repo_state.setdefault("configured_names", [])
        if configured["repo"] not in configured_names:
            configured_names.append(configured["repo"])

        old_snapshot = repo_state["snapshot"]
        new_snapshot = repository_snapshot(repo)
        popularity = repository_popularity(repo, old_snapshot)
        changed = meaningful_changes(old_snapshot, new_snapshot)
        repo_state["snapshot"] = new_snapshot
        repo_state["last_seen_at"] = to_iso8601(run_at)
        if changed:
            result.items.append(
                self._repository_updated_item(repo, configured, changed, run_at, popularity)
            )
        self.client.commit_cache(api_result)
        self._collect_repository_details(
            repo, repo_state, configured, run_at, result, initial_since=None, popularity=popularity
        )

    def _collect_repository_details_from_state(
        self,
        repo_state: dict[str, Any],
        source_config: dict[str, Any],
        run_at: datetime,
        result: WatchRunResult,
    ) -> None:
        snapshot = repo_state["snapshot"]
        repo = {
            "id": snapshot["id"],
            "full_name": snapshot["full_name"],
            "html_url": snapshot["html_url"],
            "description": snapshot.get("description"),
            "default_branch": snapshot.get("default_branch"),
            "owner": {"login": snapshot.get("owner_login")},
            "stargazers_count": snapshot.get("stars", 0),
            "forks_count": snapshot.get("forks", 0),
        }
        self._collect_repository_details(
            repo,
            repo_state,
            source_config,
            run_at,
            result,
            initial_since=None,
            popularity=repository_popularity(repo, snapshot),
        )

    def _collect_repository_details(
        self,
        repo: dict[str, Any],
        repo_state: dict[str, Any],
        source_config: dict[str, Any],
        run_at: datetime,
        result: WatchRunResult,
        *,
        initial_since: datetime | None,
        popularity: dict[str, int],
    ) -> None:
        details = repo_state.setdefault("details", {})
        first_observed = parse_iso8601(repo_state.get("first_observed_at")) or run_at
        release_since = (
            parse_iso8601(details.get("release_checked_at")) or initial_since or first_observed
        )
        commit_since = (
            parse_iso8601(details.get("commit_checked_at")) or initial_since or first_observed
        )

        try:
            self._collect_releases(
                repo, details, source_config, run_at, result, release_since, popularity
            )
        except GitHubApiError as exc:
            result.add_error(f"releases:{repo['full_name']}", exc)

        try:
            self._collect_tags(repo, details, source_config, run_at, result, popularity)
        except GitHubApiError as exc:
            result.add_error(f"tags:{repo['full_name']}", exc)

        try:
            self._collect_default_branch_head(
                repo, details, source_config, run_at, result, commit_since, popularity
            )
        except GitHubApiError as exc:
            result.add_error(f"commit:{repo['full_name']}", exc)

    def _collect_releases(
        self,
        repo: dict[str, Any],
        details: dict[str, Any],
        source_config: dict[str, Any],
        run_at: datetime,
        result: WatchRunResult,
        since: datetime,
        popularity: dict[str, int],
    ) -> None:
        path = f"/repos/{repo['full_name']}/releases"
        seen_list = [str(value) for value in details.get("seen_release_ids", [])]
        seen = set(seen_list)
        initialized = bool(details.get("release_initialized"))
        first = self.client.get_json(path, params={"per_page": 100, "page": 1}, conditional=True)
        if first.not_modified:
            details["release_checked_at"] = to_iso8601(run_at)
            return
        releases = require_list(first, path)
        pages = [releases]
        page_number = 2
        while len(pages[-1]) == 100 and page_number <= 10:
            if initialized and any(str(item.get("id")) in seen for item in pages[-1]):
                break
            if not initialized and any(
                release_time(item) and release_time(item) <= since for item in pages[-1]
            ):
                break
            page = self.client.get_json(path, params={"per_page": 100, "page": page_number})
            pages.append(require_list(page, path))
            page_number += 1

        observed_ids: list[str] = []
        for release in (item for page in pages for item in page):
            if release.get("draft"):
                continue
            release_id = str(release.get("id"))
            if release_id == "None":
                continue
            observed_ids.append(release_id)
            published = release_time(release)
            if initialized:
                should_emit = release_id not in seen
            else:
                should_emit = published is not None and published > since
            if should_emit:
                result.items.append(
                    self._release_item(repo, release, source_config, run_at, popularity)
                )

        details["seen_release_ids"] = dedupe_keep_order(observed_ids + seen_list)[:200]
        details["release_initialized"] = True
        details["release_checked_at"] = to_iso8601(run_at)
        self.client.commit_cache(first)

    def _collect_tags(
        self,
        repo: dict[str, Any],
        details: dict[str, Any],
        source_config: dict[str, Any],
        run_at: datetime,
        result: WatchRunResult,
        popularity: dict[str, int],
    ) -> None:
        path = f"/repos/{repo['full_name']}/tags"
        seen_list = [str(value) for value in details.get("seen_tags", [])]
        seen = set(seen_list)
        initialized = bool(details.get("tag_initialized"))
        first = self.client.get_json(path, params={"per_page": 100, "page": 1}, conditional=True)
        if first.not_modified:
            details["tag_checked_at"] = to_iso8601(run_at)
            return
        tags = require_list(first, path)
        pages = [tags]
        page_number = 2
        while initialized and len(pages[-1]) == 100 and page_number <= 10:
            names = {str(item.get("name")) for item in pages[-1]}
            if names & seen:
                break
            page = self.client.get_json(path, params={"per_page": 100, "page": page_number})
            pages.append(require_list(page, path))
            page_number += 1

        observed: list[str] = []
        for tag in (item for page in pages for item in page):
            name = tag.get("name")
            if not isinstance(name, str) or not name:
                continue
            observed.append(name)
            if initialized and name not in seen:
                result.items.append(self._tag_item(repo, tag, source_config, run_at, popularity))

        details["seen_tags"] = dedupe_keep_order(observed + seen_list)[:200]
        details["tag_initialized"] = True
        details["tag_checked_at"] = to_iso8601(run_at)
        self.client.commit_cache(first)

    def _collect_default_branch_head(
        self,
        repo: dict[str, Any],
        details: dict[str, Any],
        source_config: dict[str, Any],
        run_at: datetime,
        result: WatchRunResult,
        since: datetime,
        popularity: dict[str, int],
    ) -> None:
        branch = repo.get("default_branch")
        if not isinstance(branch, str) or not branch:
            return
        path = f"/repos/{repo['full_name']}/commits/{branch}"
        try:
            api_result = self.client.get_json(path, conditional=True)
        except GitHubNotFoundError:
            return
        except GitHubApiError as exc:
            if "409" in str(exc):
                return
            raise
        if api_result.not_modified:
            details["commit_checked_at"] = to_iso8601(run_at)
            return
        commit = require_object(api_result, path)
        sha = commit.get("sha")
        if not isinstance(sha, str) or not sha:
            self.client.invalidate_cache(api_result)
            raise GitHubApiError(f"Missing commit SHA from {path}")

        previous = details.get("default_branch_head")
        initialized = bool(details.get("commit_initialized"))
        committed = commit_time(commit)
        if initialized:
            should_emit = sha != previous
        else:
            should_emit = committed is not None and committed > since
        if should_emit:
            result.items.append(
                self._commit_item(repo, commit, source_config, run_at, previous, popularity)
            )

        details["default_branch_head"] = sha
        details["commit_initialized"] = True
        details["commit_checked_at"] = to_iso8601(run_at)
        self.client.commit_cache(api_result)

    def _list_account_repositories(self, login: str, account_type: str) -> list[dict[str, Any]]:
        if account_type == "organization":
            return self.client.get_paginated(
                f"/orgs/{login}/repos",
                params={"type": "public", "sort": "full_name", "direction": "asc", "per_page": 100},
            )
        return self.client.get_paginated(
            f"/users/{login}/repos",
            params={"type": "owner", "sort": "full_name", "direction": "asc", "per_page": 100},
        )

    def _ensure_repository_state(self, repo: dict[str, Any], run_at: datetime) -> dict[str, Any]:
        repo_id = str(repo["id"])
        existing = self.state["repositories"].get(repo_id)
        if existing is not None:
            existing["snapshot"] = repository_snapshot(repo)
            existing["last_seen_at"] = to_iso8601(run_at)
            return existing
        state = {
            "first_observed_at": to_iso8601(run_at),
            "last_seen_at": to_iso8601(run_at),
            "snapshot": repository_snapshot(repo),
            "details": {},
        }
        self.state["repositories"][repo_id] = state
        return state

    def _repository_state_for_configured_name(self, full_name: str) -> dict[str, Any] | None:
        target = full_name.lower()
        for repo_state in self.state["repositories"].values():
            snapshot_name = repo_state.get("snapshot", {}).get("full_name", "").lower()
            configured_names = {name.lower() for name in repo_state.get("configured_names", [])}
            if snapshot_name == target or target in configured_names:
                return repo_state
        return None

    def _repository_created_item(
        self,
        repo: dict[str, Any],
        source_config: dict[str, Any],
        run_at: datetime,
        popularity: dict[str, int],
    ) -> NormalizedItem:
        repo_id = str(repo["id"])
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
            updated_at=repo.get("updated_at"),
            discovered_at=to_iso8601(run_at),
            topics=list(source_config.get("topics", [])),
            priority=source_priority(source_config),
            metadata={
                "action": "created",
                "homepage": repo.get("homepage"),
                "fork": bool(repo.get("fork")),
                "archived": bool(repo.get("archived")),
                **popularity,
            },
        )

    def _repository_updated_item(
        self,
        repo: dict[str, Any],
        source_config: dict[str, Any],
        changes: dict[str, dict[str, Any]],
        run_at: datetime,
        popularity: dict[str, int],
    ) -> NormalizedItem:
        repo_id = str(repo["id"])
        fingerprint = hashlib.sha256(
            json.dumps(changes, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        source_id = f"{repo_id}:metadata:{repo.get('updated_at')}:{fingerprint}"
        return NormalizedItem(
            id=f"github:event:{source_id}",
            source="github",
            source_id=source_id,
            kind="event",
            title=f"{repo['full_name']} repository metadata updated",
            url=repo["html_url"],
            summary=repo.get("description"),
            organization=owner_login(repo),
            published_at=repo.get("updated_at"),
            updated_at=repo.get("updated_at"),
            discovered_at=to_iso8601(run_at),
            topics=list(source_config.get("topics", [])),
            priority=source_priority(source_config),
            metadata={"action": "metadata_updated", "changes": changes, **popularity},
        )

    def _repository_missing_item(
        self,
        snapshot: dict[str, Any],
        source_config: dict[str, Any],
        previous_checked: str,
        run_at: datetime,
    ) -> NormalizedItem:
        repo_id = str(snapshot["id"])
        source_name = source_config.get("login", "unknown")
        source_id = f"{repo_id}:missing:{source_name.lower()}:{previous_checked}"
        return NormalizedItem(
            id=f"github:event:{source_id}",
            source="github",
            source_id=source_id,
            kind="event",
            title=f"{snapshot['full_name']} no longer listed under {source_name}",
            url=snapshot["html_url"],
            summary=snapshot.get("description"),
            organization=snapshot.get("owner_login"),
            discovered_at=to_iso8601(run_at),
            topics=list(source_config.get("topics", [])),
            priority=source_priority(source_config),
            metadata={"action": "missing_from_account", "account": source_name},
        )

    def _release_item(
        self,
        repo: dict[str, Any],
        release: dict[str, Any],
        source_config: dict[str, Any],
        run_at: datetime,
        popularity: dict[str, int],
    ) -> NormalizedItem:
        release_id = str(release["id"])
        source_id = f"{repo['id']}:release:{release_id}"
        tag = release.get("tag_name") or "release"
        name = release.get("name") or tag
        return NormalizedItem(
            id=f"github:release:{source_id}",
            source="github",
            source_id=source_id,
            kind="release",
            title=f"{repo['full_name']} {name}",
            url=release.get("html_url") or repo["html_url"],
            summary=release.get("body"),
            organization=owner_login(repo),
            published_at=release.get("published_at") or release.get("created_at"),
            updated_at=release.get("updated_at"),
            discovered_at=to_iso8601(run_at),
            topics=list(source_config.get("topics", [])),
            priority=source_priority(source_config),
            metadata={
                "action": "released",
                "tag_name": tag,
                "prerelease": bool(release.get("prerelease")),
                "draft": bool(release.get("draft")),
                **popularity,
            },
        )

    def _tag_item(
        self,
        repo: dict[str, Any],
        tag: dict[str, Any],
        source_config: dict[str, Any],
        run_at: datetime,
        popularity: dict[str, int],
    ) -> NormalizedItem:
        name = str(tag["name"])
        source_id = f"{repo['id']}:tag:{name}"
        commit = tag.get("commit") or {}
        return NormalizedItem(
            id=f"github:tag:{source_id}",
            source="github",
            source_id=source_id,
            kind="tag",
            title=f"{repo['full_name']} tagged {name}",
            url=tag.get("zipball_url") or repo["html_url"],
            organization=owner_login(repo),
            discovered_at=to_iso8601(run_at),
            topics=list(source_config.get("topics", [])),
            priority=source_priority(source_config),
            metadata={
                "action": "tagged",
                "tag_name": name,
                "commit_sha": commit.get("sha"),
                **popularity,
            },
        )

    def _commit_item(
        self,
        repo: dict[str, Any],
        commit: dict[str, Any],
        source_config: dict[str, Any],
        run_at: datetime,
        previous_head: str | None,
        popularity: dict[str, int],
    ) -> NormalizedItem:
        sha = str(commit["sha"])
        source_id = f"{repo['id']}:commit:{sha}"
        nested = commit.get("commit") or {}
        message = nested.get("message") or sha[:12]
        summary = message.splitlines()[0] if isinstance(message, str) else None
        return NormalizedItem(
            id=f"github:commit:{source_id}",
            source="github",
            source_id=source_id,
            kind="commit",
            title=f"{repo['full_name']} default branch advanced",
            url=commit.get("html_url") or repo["html_url"],
            summary=summary,
            organization=owner_login(repo),
            published_at=commit_time_iso(commit),
            discovered_at=to_iso8601(run_at),
            topics=list(source_config.get("topics", [])),
            priority=source_priority(source_config),
            metadata={
                "action": "default_branch_advanced",
                "sha": sha,
                "previous_head": previous_head,
                "default_branch": repo.get("default_branch"),
                **popularity,
            },
        )


def repository_snapshot(repo: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": repo["id"],
        "name": repo.get("name"),
        "full_name": repo["full_name"],
        "html_url": repo["html_url"],
        "owner_login": owner_login(repo),
        "description": repo.get("description"),
        "homepage": repo.get("homepage"),
        "topics": sorted(repo.get("topics") or []),
        "archived": bool(repo.get("archived")),
        "disabled": bool(repo.get("disabled")),
        "fork": bool(repo.get("fork")),
        "visibility": repo.get("visibility"),
        "default_branch": repo.get("default_branch"),
        "created_at": repo.get("created_at"),
        "updated_at": repo.get("updated_at"),
        "pushed_at": repo.get("pushed_at"),
        "stars": int(repo.get("stargazers_count") or 0),
        "forks": int(repo.get("forks_count") or 0),
    }


def repository_popularity(
    repo: dict[str, Any], previous_snapshot: dict[str, Any] | None
) -> dict[str, int]:
    stars = int(repo.get("stargazers_count") or 0)
    forks = int(repo.get("forks_count") or 0)
    previous_stars = int(previous_snapshot.get("stars") or 0) if previous_snapshot else stars
    return {"stars": stars, "forks": forks, "stars_delta": stars - previous_stars}


def meaningful_changes(old: dict[str, Any], new: dict[str, Any]) -> dict[str, dict[str, Any]]:
    changes: dict[str, dict[str, Any]] = {}
    for key in MEANINGFUL_REPOSITORY_FIELDS:
        if old.get(key) != new.get(key):
            changes[key] = {"old": old.get(key), "new": new.get(key)}
    return changes


def owner_login(repo: dict[str, Any]) -> str | None:
    owner = repo.get("owner") or {}
    value = owner.get("login") if isinstance(owner, dict) else None
    if isinstance(value, str):
        return value
    full_name = repo.get("full_name")
    if isinstance(full_name, str) and "/" in full_name:
        return full_name.split("/", 1)[0]
    return None


def source_priority(config: dict[str, Any]) -> dict[str, float | None]:
    return {"source": 1.0 if config.get("priority") == "high" else 0.5}


def release_time(release: dict[str, Any]) -> datetime | None:
    return parse_iso8601(release.get("published_at") or release.get("created_at"))


def commit_time(commit: dict[str, Any]) -> datetime | None:
    nested = commit.get("commit") or {}
    committer = nested.get("committer") or {}
    author = nested.get("author") or {}
    return parse_iso8601(committer.get("date") or author.get("date"))


def commit_time_iso(commit: dict[str, Any]) -> str | None:
    value = commit_time(commit)
    return to_iso8601(value) if value else None


def require_object(result: ApiResult, path: str) -> dict[str, Any]:
    if not isinstance(result.data, dict):
        raise GitHubApiError(f"Expected object response from {path}")
    return result.data


def require_list(result: ApiResult, path: str) -> list[dict[str, Any]]:
    if not isinstance(result.data, list):
        raise GitHubApiError(f"Expected list response from {path}")
    return [item for item in result.data if isinstance(item, dict)]


def dedupe_keep_order(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
