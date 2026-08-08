from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from ..analytics.archive import archive_index_from_dict, search_archive
from ..config import load_analytics
from ..models import parse_iso8601
from ..runtime import RuntimePaths
from ..storage import JsonDocumentStore

ROOT = Path(__file__).resolve().parents[3]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search the derived research archive")
    parser.add_argument("query", nargs="?", default="", help="Words that must match the record")
    parser.add_argument("--topic", action="append", default=[])
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--kind", action="append", default=[])
    parser.add_argument("--since", help="UTC timestamp or YYYY-MM-DD")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--include-hidden", action="store_true")
    parser.add_argument("--work-root", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = RuntimePaths.resolve(args.work_root)
    config = load_analytics(
        ROOT / "config/analytics.yaml", ROOT / "config/schemas/analytics.schema.json"
    )
    path = paths.archive / "index.json"
    data = JsonDocumentStore(path).load()
    if not data:
        raise SystemExit("Archive index is missing; run build_trends first")
    index = archive_index_from_dict(data)

    maximum = int(config["archive"]["maximum_search_limit"])
    default = int(config["archive"]["default_search_limit"])
    limit = default if args.limit is None else args.limit
    if limit < 1 or limit > maximum:
        raise SystemExit(f"--limit must be between 1 and {maximum}")

    since = parse_since(args.since)
    records = search_archive(
        index,
        query=args.query,
        topics=set(args.topic),
        sources=set(args.source),
        kinds=set(args.kind),
        since=since,
        include_hidden=args.include_hidden,
        limit=limit,
    )
    print(
        json.dumps(
            {"count": len(records), "records": [record.to_dict() for record in records]}, indent=2
        )
    )
    return 0


def parse_since(value: str | None):
    if value is None:
        return None
    if len(value) == 10:
        try:
            return datetime.fromisoformat(value).replace(tzinfo=UTC)
        except ValueError as exc:
            raise SystemExit("--since must use YYYY-MM-DD or an ISO 8601 UTC timestamp") from exc
    parsed = parse_iso8601(value)
    if parsed is None:
        raise SystemExit("--since must use YYYY-MM-DD or an ISO 8601 UTC timestamp")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
