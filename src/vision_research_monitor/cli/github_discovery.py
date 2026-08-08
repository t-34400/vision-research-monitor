from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from ..classification.semantic import SemanticClassificationPipeline
from ..config import load_github_discovery, load_semantic, load_taxonomy, load_venues
from ..github.auto_watch import normalize_registry, update_auto_watch_registry
from ..github.client import GitHubClient
from ..github.discovery import GitHubDiscoveryCollector
from ..models import parse_iso8601, to_iso8601
from ..runtime import RuntimePaths
from ..storage import JsonDocumentStore, JsonlItemStore, JsonStateStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discover relevant GitHub repositories")
    parser.add_argument("--taxonomy", type=Path, default=Path("config/taxonomy.yaml"))
    parser.add_argument(
        "--taxonomy-schema", type=Path, default=Path("config/schemas/taxonomy.schema.json")
    )
    parser.add_argument("--venues", type=Path, default=Path("config/venues.yaml"))
    parser.add_argument(
        "--venues-schema", type=Path, default=Path("config/schemas/venues.schema.json")
    )
    parser.add_argument("--config", type=Path, default=Path("config/github_discovery.yaml"))
    parser.add_argument(
        "--config-schema", type=Path, default=Path("config/schemas/github-discovery.schema.json")
    )
    parser.add_argument("--semantic", type=Path, default=Path("config/semantic.yaml"))
    parser.add_argument(
        "--semantic-schema", type=Path, default=Path("config/schemas/semantic.schema.json")
    )
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--items", type=Path)
    parser.add_argument("--auto-watch-registry", type=Path)
    parser.add_argument("--from", dest="from_time")
    parser.add_argument("--to", dest="to_time")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = RuntimePaths.resolve(args.work_root)
    taxonomy = load_taxonomy(args.taxonomy, args.taxonomy_schema)
    venues = load_venues(args.venues, args.venues_schema)
    topic_ids = {topic["id"] for topic in taxonomy["topics"]}
    venue_ids = {venue["id"] for venue in venues["venues"]}
    config = load_github_discovery(args.config, args.config_schema, topic_ids, venue_ids)
    semantic = load_semantic(args.semantic, args.semantic_schema, topic_ids)
    classifier = SemanticClassificationPipeline(taxonomy, semantic)

    explicit_window = args.from_time is not None or args.to_time is not None
    if explicit_window and not (args.from_time and args.to_time):
        raise SystemExit("--from and --to must be provided together")
    window_start = parse_iso8601(args.from_time) if args.from_time else None
    window_end = parse_iso8601(args.to_time) if args.to_time else None
    if explicit_window and (window_start is None or window_end is None):
        raise SystemExit("--from and --to must be valid ISO 8601 timestamps")

    state_store = JsonStateStore(args.state or paths.state / "github_discovery.json")
    state = state_store.load()
    registry_store = JsonDocumentStore(
        args.auto_watch_registry or paths.state / "github_auto_watch.json"
    )
    registry = normalize_registry(registry_store.load())
    item_store = JsonlItemStore(args.items or paths.items)
    token = os.environ.get("GH_DISCOVERY_TOKEN") or os.environ.get("GITHUB_TOKEN")
    run_at = datetime.now(UTC)

    with GitHubClient(token, state["http_cache"]) as client:
        collector = GitHubDiscoveryCollector(
            client,
            state,
            config,
            taxonomy,
            venues,
            classifier,
            progress=lambda target: print(
                f"[github-discovery] {target}", file=sys.stderr, flush=True
            ),
        )
        result = collector.collect(run_at, window_start=window_start, window_end=window_end)

    written = item_store.append(result.items)
    if explicit_window:
        auto_watch = {
            "eligible": 0,
            "promoted": 0,
            "tracked": len(registry["repositories"]),
            "updated": False,
        }
    else:
        auto_watch = update_auto_watch_registry(
            registry, result.items, config["auto_watch"], run_at
        )
        auto_watch["updated"] = True
    if result.failed_queries == 0 and not explicit_window:
        state["last_successful_at"] = to_iso8601(run_at)
    state_store.save(state)
    registry_store.save(registry)

    summary = {
        "window_start": result.window_start,
        "window_end": result.window_end,
        "raw_candidates": result.raw_candidates,
        "collected": len(result.items),
        "rejected": result.rejected_candidates,
        "rejected_for_context": result.rejected_for_context,
        "written": written,
        "failed_queries": result.failed_queries,
        "search_hits_by_query": result.search_hits_by_query,
        "accepted_by_query": result.accepted_by_query,
        "research_quality_by_category": result.research_quality_by_category,
        "auto_watch": auto_watch,
        "checkpoint_advanced": result.failed_queries == 0 and not explicit_window,
        "diagnostics": result.diagnostics,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if result.failed_queries else 0


if __name__ == "__main__":
    sys.exit(main())
