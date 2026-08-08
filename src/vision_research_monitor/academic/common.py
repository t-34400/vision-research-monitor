from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ..models import NormalizedItem, parse_iso8601, to_iso8601


class AcademicCoverageError(RuntimeError):
    pass


@dataclass(slots=True)
class AcademicRunResult:
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
    run_at = run_at.astimezone(UTC)
    previous = parse_iso8601(checkpoint)
    if previous is None:
        return run_at - timedelta(hours=config["initial_lookback_hours"]), run_at

    elapsed = run_at - previous
    maximum = timedelta(hours=config["max_catchup_hours"])
    if elapsed > maximum:
        raise AcademicCoverageError(
            f"{source_name} checkpoint is {elapsed.total_seconds() / 3600:.1f} hours old; "
            f"maximum automatic catch-up is {config['max_catchup_hours']} hours"
        )
    return previous - timedelta(minutes=config["overlap_minutes"]), run_at


def normalize_window(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    if start >= end:
        raise ValueError("Academic discovery window start must be before its end")
    return start, end


def initialize_result(start: datetime, end: datetime) -> AcademicRunResult:
    return AcademicRunResult(window_start=to_iso8601(start), window_end=to_iso8601(end))
