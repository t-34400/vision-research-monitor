from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from vision_research_monitor.classification.semantic import SemanticClassificationPipeline
from vision_research_monitor.config import load_semantic, load_sources, load_taxonomy, load_venues
from vision_research_monitor.http import HttpClient
from vision_research_monitor.models import parse_iso8601
from vision_research_monitor.sources.cvf import CVFCollector
from vision_research_monitor.storage import JsonlItemStore, JsonStateStore

ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect newly published CVF Open Access papers")
    parser.add_argument("--run-at")
    args = parser.parse_args()

    run_at = parse_iso8601(args.run_at) if args.run_at else datetime.now(UTC)
    if run_at is None:
        parser.error("--run-at must be an ISO 8601 timestamp")

    taxonomy = load_taxonomy(
        ROOT / "config/taxonomy.yaml", ROOT / "config/schemas/taxonomy.schema.json"
    )
    venues = load_venues(ROOT / "config/venues.yaml", ROOT / "config/schemas/venues.schema.json")
    topic_ids = {topic["id"] for topic in taxonomy["topics"]}
    config = load_sources(
        ROOT / "config/sources.yaml",
        ROOT / "config/schemas/sources.schema.json",
        {venue["id"] for venue in venues["venues"]},
    )
    semantic = load_semantic(
        ROOT / "config/semantic.yaml",
        ROOT / "config/schemas/semantic.schema.json",
        topic_ids,
    )
    classifier = SemanticClassificationPipeline(taxonomy, semantic)
    state_store = JsonStateStore(ROOT / "data/state/cvf.json")
    state = state_store.load()
    if not config["cvf"]["enabled"]:
        print(json.dumps({"found": 0, "written": 0, "failed_targets": 0, "disabled": True}))
        return 0

    with HttpClient(
        config["cvf"]["base_url"],
        user_agent=config["cvf"]["user_agent"],
    ) as client:
        result = CVFCollector(client, state, config, taxonomy, classifier).collect(run_at)

    written = JsonlItemStore(ROOT / "data/items").append(result.items)
    if result.failed_targets == 0:
        state_store.save(state)

    print(
        json.dumps(
            {
                "found": len(result.items),
                "written": written,
                "failed_targets": result.failed_targets,
            }
        )
    )
    for diagnostic in result.diagnostics:
        print(json.dumps(diagnostic), flush=True)
    return 1 if result.failed_targets else 0


if __name__ == "__main__":
    raise SystemExit(main())
