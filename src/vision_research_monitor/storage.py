from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator

from .models import NormalizedItem, parse_iso8601


class JsonStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "version": 1,
                "accounts": {},
                "repositories": {},
                "http_cache": {},
            }
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ValueError(f"Unsupported state version in {self.path}")
        data.setdefault("accounts", {})
        data.setdefault("repositories", {})
        data.setdefault("http_cache", {})
        return data

    def save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)


class JsonlItemStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._known_ids = self._load_known_ids()

    def _load_known_ids(self) -> set[str]:
        if not self.root.exists():
            return set()
        known: set[str] = set()
        for path in self.root.rglob("*.jsonl"):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc
                item_id = record.get("id")
                if isinstance(item_id, str):
                    known.add(item_id)
        return known

    def iter_records(self) -> Iterator[dict[str, Any]]:
        if not self.root.exists():
            return
        for path in sorted(self.root.rglob("*.jsonl")):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc
                if not isinstance(record, dict):
                    raise ValueError(f"Expected object JSONL record at {path}:{line_number}")
                yield record

    def load_items(self) -> list[NormalizedItem]:
        return [NormalizedItem.from_dict(record) for record in self.iter_records()]

    def append(self, items: Iterable[NormalizedItem]) -> int:
        grouped: dict[Path, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            if item.id in self._known_ids:
                continue
            discovered = parse_iso8601(item.discovered_at)
            if discovered is None:
                raise ValueError(f"Missing discovered_at for {item.id}")
            path = self.root / f"{discovered.year:04d}" / f"{discovered.month:02d}" / f"{discovered.day:02d}.jsonl"
            grouped[path].append(item.to_dict())
            self._known_ids.add(item.id)

        written = 0
        for path, records in grouped.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            existing = path.read_text(encoding="utf-8") if path.exists() else ""
            payload = existing + "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(payload, encoding="utf-8")
            os.replace(temporary, path)
            written += len(records)
        return written


class JsonDocumentStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object in {self.path}")
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)
