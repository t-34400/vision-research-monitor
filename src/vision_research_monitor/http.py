from __future__ import annotations

import email.utils
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx


class HttpApiError(RuntimeError):
    pass


@dataclass(slots=True)
class HttpResult:
    data: Any
    status_code: int
    headers: Mapping[str, str]


class HttpClient:
    def __init__(
        self,
        base_url: str,
        *,
        user_agent: str = "vision-research-monitor/0.1",
        token: str | None = None,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        max_retries: int = 3,
        max_retry_wait: float = 120.0,
    ) -> None:
        headers = {"Accept": "application/json", "User-Agent": user_agent}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            base_url=base_url,
            headers=headers,
            follow_redirects=True,
            timeout=45.0,
            transport=transport,
        )
        self.sleeper = sleeper
        self.max_retries = max_retries
        self.max_retry_wait = max_retry_wait

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def get_json(self, path: str, *, params: Mapping[str, Any] | None = None) -> HttpResult:
        response = self._get(path, params=params)
        try:
            data = response.json()
        except ValueError as exc:
            raise HttpApiError(f"Expected JSON response from {response.request.url}") from exc
        return HttpResult(data=data, status_code=response.status_code, headers=response.headers)

    def get_text(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        accept: str = "text/html, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
    ) -> HttpResult:
        response = self._get(path, params=params, headers={"Accept": accept})
        return HttpResult(
            data=response.text, status_code=response.status_code, headers=response.headers
        )

    def _get(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.get(path, params=params, headers=headers)
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    raise HttpApiError(f"HTTP transport failure: {exc}") from exc
                self.sleeper(min(2**attempt, 30.0))
                continue

            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt >= self.max_retries:
                    raise HttpApiError(
                        f"HTTP retry limit exceeded ({response.status_code}): {response.request.url}"
                    )
                delay = self._retry_delay(response, attempt)
                if delay > self.max_retry_wait:
                    raise HttpApiError(
                        f"HTTP retry wait ({delay:.0f}s) exceeds configured maximum: {response.request.url}"
                    )
                self.sleeper(delay)
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise HttpApiError(
                    f"HTTP request failed ({response.status_code}): {response.request.url}"
                ) from exc
            return response
        raise AssertionError("retry loop exhausted unexpectedly")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                try:
                    parsed = email.utils.parsedate_to_datetime(retry_after)
                except (TypeError, ValueError):
                    pass
                else:
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=UTC)
                    return max(0.0, (parsed - datetime.now(UTC)).total_seconds())
        return min(2**attempt, 30.0)
