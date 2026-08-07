from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..config import load_taxonomy, load_watchlist
from ..github.client import GitHubClient
from ..github.watch import GitHubWatchCollector
from ..storage import JsonlItemStore, JsonStateStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect changes from configured GitHub watch targets")
    parser.add_argument("--taxonomy", type=Path, default=Path("config/taxonomy.yaml"))
    parser.add_argument("--taxonomy-schema", type=Path, default=Path("config/schemas/taxonomy.schema.json"))
    parser.add_argument("--watchlist", type=Path, default=Path("config/github_watchlist.yaml"))
    parser.add_argument("--watchlist-schema", type=Path, default=Path("config/schemas/watchlist.schema.json"))
    parser.add_argument("--state", type=Path, default=Path("data/state/github_watch.json"))
    parser.add_argument("--items", type=Path, default=Path("data/items"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    taxonomy = load_taxonomy(args.taxonomy, args.taxonomy_schema)
    topic_ids = {topic["id"] for topic in taxonomy["topics"]}
    watchlist = load_watchlist(args.watchlist, args.watchlist_schema, topic_ids)

    state_store = JsonStateStore(args.state)
    state = state_store.load()
    item_store = JsonlItemStore(args.items)
    token = os.environ.get("GH_WATCH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    run_at = datetime.now(timezone.utc)

    with GitHubClient(token, state["http_cache"]) as client:
        collector = GitHubWatchCollector(client, state, watchlist)
        result = collector.collect(run_at)

    written = item_store.append(result.items)
    state_store.save(state)

    summary = {
        "collected": len(result.items),
        "written": written,
        "failed_targets": result.failed_targets,
        "diagnostics": result.diagnostics,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if result.failed_targets else 0


if __name__ == "__main__":
    sys.exit(main())
