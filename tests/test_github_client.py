import httpx

from vision_research_monitor.github.client import GitHubClient


def test_conditional_request_uses_committed_etag() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.headers.get("if-none-match") == '"etag-1"':
            return httpx.Response(304, headers={"ETag": '"etag-1"'})
        return httpx.Response(200, json={"id": 1}, headers={"ETag": '"etag-1"'})

    cache: dict[str, object] = {}
    with GitHubClient(None, cache, transport=httpx.MockTransport(handler)) as client:
        first = client.get_json("/repos/example/project", conditional=True)
        client.commit_cache(first)
        second = client.get_json("/repos/example/project", conditional=True)

    assert first.data == {"id": 1}
    assert second.not_modified is True
    assert requests[1].headers["if-none-match"] == '"etag-1"'


def test_server_error_retries_with_backoff() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, json={"message": "temporary"})
        return httpx.Response(200, json={"ok": True})

    with GitHubClient(
        None,
        {},
        transport=httpx.MockTransport(handler),
        sleeper=delays.append,
    ) as client:
        result = client.get_json("/rate-limited")

    assert result.data == {"ok": True}
    assert attempts == 2
    assert delays == [1]
