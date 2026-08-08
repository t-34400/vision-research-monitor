from __future__ import annotations

from typing import Any, Mapping

from ..http import HttpApiError, HttpClient, HttpResult

AcademicApiError = HttpApiError


class AcademicHttpClient(HttpClient):
    def get_text(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        accept: str = "application/atom+xml, application/xml;q=0.9, text/xml;q=0.8",
    ) -> HttpResult:
        return super().get_text(path, params=params, accept=accept)


__all__ = ["AcademicApiError", "AcademicHttpClient", "HttpResult"]
