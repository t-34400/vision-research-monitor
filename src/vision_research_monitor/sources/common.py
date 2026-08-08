from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ..models import NormalizedItem, parse_iso8601, to_iso8601


class SourceCoverageError(RuntimeError):
    pass


@dataclass(slots=True)
class SourceRunResult:
    items: list[NormalizedItem] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    failed_targets: int = 0
    window_start: str | None = None
    window_end: str | None = None

    def add_error(self, target: str, exc: Exception) -> None:
        self.failed_targets += 1
        self.diagnostics.append({"level": "error", "target": target, "message": str(exc)})

    def add_warning(self, target: str, message: str) -> None:
        self.diagnostics.append({"level": "warning", "target": target, "message": message})


def collection_window(
    run_at: datetime,
    checkpoint: str | None,
    config: dict[str, Any],
    *,
    source_name: str,
) -> tuple[datetime, datetime]:
    run_at = run_at.astimezone(timezone.utc)
    previous = parse_iso8601(checkpoint)
    if previous is None:
        return run_at - timedelta(hours=int(config["initial_lookback_hours"])), run_at

    elapsed = run_at - previous
    maximum = timedelta(hours=int(config["max_catchup_hours"]))
    if elapsed > maximum:
        raise SourceCoverageError(
            f"{source_name} checkpoint is {elapsed.total_seconds() / 3600:.1f} hours old; "
            f"maximum automatic catch-up is {config['max_catchup_hours']} hours"
        )
    return previous - timedelta(minutes=int(config["overlap_minutes"])), run_at


def normalize_window(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    if start >= end:
        raise ValueError("Source collection window start must be before its end")
    return start, end


def initialize_result(start: datetime | None = None, end: datetime | None = None) -> SourceRunResult:
    return SourceRunResult(
        window_start=to_iso8601(start) if start is not None else None,
        window_end=to_iso8601(end) if end is not None else None,
    )
