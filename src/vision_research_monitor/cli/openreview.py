from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from vision_research_monitor.academic.http import AcademicHttpClient
from vision_research_monitor.academic.openreview import OpenReviewCollector
from vision_research_monitor.classification.semantic import SemanticClassificationPipeline
from vision_research_monitor.config import load_academic, load_semantic, load_taxonomy, load_venues
from vision_research_monitor.models import parse_iso8601, to_iso8601
from vision_research_monitor.storage import JsonStateStore, JsonlItemStore


ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect relevant OpenReview papers")
    parser.add_argument("--from", dest="window_start")
    parser.add_argument("--to", dest="window_end")
    parser.add_argument("--run-at")
    args = parser.parse_args()

    run_at = parse_iso8601(args.run_at) if args.run_at else datetime.now(timezone.utc)
    if run_at is None:
        parser.error("--run-at must be an ISO 8601 timestamp")
    explicit = args.window_start is not None or args.window_end is not None
    if explicit and not (args.window_start and args.window_end):
        parser.error("--from and --to must be provided together")
    start = parse_iso8601(args.window_start) if explicit else None
    end = parse_iso8601(args.window_end) if explicit else None

    taxonomy = load_taxonomy(ROOT / "config/taxonomy.yaml", ROOT / "config/schemas/taxonomy.schema.json")
    venues = load_venues(ROOT / "config/venues.yaml", ROOT / "config/schemas/venues.schema.json")
    config = load_academic(
        ROOT / "config/academic.yaml",
        ROOT / "config/schemas/academic.schema.json",
        {venue["id"] for venue in venues["venues"]},
    )
    semantic = load_semantic(
        ROOT / "config/semantic.yaml",
        ROOT / "config/schemas/semantic.schema.json",
        {topic["id"] for topic in taxonomy["topics"]},
    )
    classifier = SemanticClassificationPipeline(taxonomy, semantic)
    state_store = JsonStateStore(ROOT / "data/state/openreview.json")
    state = state_store.load()

    with AcademicHttpClient(
        config["openreview"]["base_url"],
        token=os.environ.get("OPENREVIEW_TOKEN"),
    ) as client:
        result = OpenReviewCollector(client, state, config, taxonomy, classifier).collect(
            run_at,
            window_start=start,
            window_end=end,
            explicit_backfill=explicit,
        )

    written = JsonlItemStore(ROOT / "data/items").append(result.items)
    if result.failed_targets == 0 and not explicit:
        state.setdefault("academic", {}).setdefault("openreview", {})["last_successful_at"] = to_iso8601(run_at)
        state_store.save(state)

    print(json.dumps({"found": len(result.items), "written": written, "failed_targets": result.failed_targets}))
    for diagnostic in result.diagnostics:
        print(json.dumps(diagnostic), flush=True)
    return 1 if result.failed_targets else 0


if __name__ == "__main__":
    raise SystemExit(main())
