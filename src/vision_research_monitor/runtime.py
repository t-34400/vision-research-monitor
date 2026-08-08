from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2].resolve()
WORK_ROOT_ENV = "VRM_WORK_ROOT"


@dataclass(frozen=True)
class RuntimePaths:
    root: Path

    @classmethod
    def resolve(cls, work_root: Path | str | None = None) -> RuntimePaths:
        value: Path | str | None = work_root
        if value is None:
            configured = os.environ.get(WORK_ROOT_ENV)
            value = configured if configured else None

        if value is None:
            root = PROJECT_ROOT
        else:
            root = Path(value).expanduser()
            if not root.is_absolute():
                root = PROJECT_ROOT / root

        return cls(root=root.resolve(strict=False))

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def items(self) -> Path:
        return self.data / "items"

    @property
    def state(self) -> Path:
        return self.data / "state"

    @property
    def entities(self) -> Path:
        return self.data / "entities"

    @property
    def ranking(self) -> Path:
        return self.data / "ranking"

    @property
    def analytics(self) -> Path:
        return self.data / "analytics"

    @property
    def archive(self) -> Path:
        return self.data / "archive"

    @property
    def daily_reports(self) -> Path:
        return self.reports / "daily"

    @property
    def trend_reports(self) -> Path:
        return self.reports / "trends"


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)
