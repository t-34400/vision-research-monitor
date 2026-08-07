from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

import httpx


API_VERSION = "2026-03-10"


class GitHubApiError(RuntimeError):
    pass


class GitHubNotFoundError(GitHubApiError):
    pass


class GitHubRateLimitError(GitHubApiError):
    pass


@dataclass(slots=True)
class ApiResult:
    data: Any
    status_code: int
    headers: Mapping[str, str]
    cache_key: str | None = None
    not_modified: bool = False


class GitHubClient:
    def __init__(
        self,
        token: str | None,
        cache: dict[str, Any],
        *,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        max_retries: int = 3,
        max_retry_wait: float = 120.0,
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "vision-research-monitor",
            "X-GitHub-Api-Version": API_VERSION,
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            base_url="https://api.github.com",
            headers=headers,
            follow_redirects=True,
            timeout=30.0,
            transport=transport,
        )
        self.cache = cache
        self.sleeper = sleeper
        self.max_retries = max_retries
        self.max_retry_wait = max_retry_wait

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    @staticmethod
    def _cache_key(path: str, params: Mapping[str, Any] | None) -> str:
        if not params:
            return path
        normalized = sorted((key, str(value)) for key, value in params.items())
        return f"{path}?{urlencode(normalized)}"

    def commit_cache(self, result: ApiResult) -> None:
        if result.cache_key is None or result.not_modified:
            return
        etag = result.headers.get("etag")
        last_modified = result.headers.get("last-modified")
        if not etag and not last_modified:
            return
        entry: dict[str, str] = {}
        if etag:
            entry["etag"] = etag
        if last_modified:
            entry["last_modified"] = last_modified
        self.cache[result.cache_key] = entry

    def invalidate_cache(self, result: ApiResult) -> None:
        if result.cache_key:
            self.cache.pop(result.cache_key, None)

    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        conditional: bool = False,
    ) -> ApiResult:
        cache_key = self._cache_key(path, params) if conditional else None
        request_headers: dict[str, str] = {}
        if cache_key:
            cached = self.cache.get(cache_key, {})
            if cached.get("etag"):
                request_headers["If-None-Match"] = cached["etag"]
            if cached.get("last_modified"):
                request_headers["If-Modified-Since"] = cached["last_modified"]

        for attempt in range(self.max_retries + 1):
            response = self._client.get(path, params=params, headers=request_headers)
            if response.status_code == 304:
                return ApiResult(None, 304, response.headers, cache_key=cache_key, not_modified=True)
            if response.status_code == 404:
                raise GitHubNotFoundError(f"GitHub resource not found: {response.request.url}")
            if self._should_retry_rate_limit(response):
                self._retry_or_raise(response, attempt, rate_limited=True)
                continue
            if response.status_code == 429 or 500 <= response.status_code < 600:
                self._retry_or_raise(response, attempt, rate_limited=response.status_code == 429)
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise GitHubApiError(f"GitHub API request failed ({response.status_code}): {response.request.url}") from exc
            return ApiResult(response.json(), response.status_code, response.headers, cache_key=cache_key)
        raise AssertionError("retry loop exhausted unexpectedly")

    def get_paginated(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        max_pages: int = 100,
    ) -> list[dict[str, Any]]:
        base_params = dict(params or {})
        per_page = int(base_params.setdefault("per_page", 100))
        records: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            page_params = dict(base_params)
            page_params["page"] = page
            result = self.get_json(path, params=page_params)
            data = result.data
            if not isinstance(data, list):
                raise GitHubApiError(f"Expected list response from {path}")
            records.extend(item for item in data if isinstance(item, dict))
            if len(data) < per_page:
                return records
        raise GitHubApiError(f"Pagination limit exceeded for {path}")

    def _should_retry_rate_limit(self, response: httpx.Response) -> bool:
        if response.status_code != 403:
            return False
        if response.headers.get("x-ratelimit-remaining") == "0" or response.headers.get("retry-after"):
            return True
        message = response.text.lower()
        return "secondary rate limit" in message or "abuse detection" in message

    def _retry_or_raise(self, response: httpx.Response, attempt: int, *, rate_limited: bool) -> None:
        if attempt >= self.max_retries:
            error = GitHubRateLimitError if rate_limited else GitHubApiError
            raise error(f"GitHub API retry limit exceeded ({response.status_code}): {response.request.url}")
        delay = self._retry_delay(response, attempt, rate_limited=rate_limited)
        if delay > self.max_retry_wait:
            raise GitHubRateLimitError(
                f"GitHub rate limit wait ({delay:.0f}s) exceeds configured maximum: {response.request.url}"
            )
        self.sleeper(delay)

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int, *, rate_limited: bool) -> float:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        if response.headers.get("x-ratelimit-remaining") == "0":
            reset = response.headers.get("x-ratelimit-reset")
            if reset:
                try:
                    return max(0.0, float(reset) - time.time() + 1.0)
                except ValueError:
                    pass
        if rate_limited:
            return 60.0 * (2**attempt)
        return min(2**attempt, 30.0)
