from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..config import load_linking, load_reporting, load_taxonomy, load_venues
from ..linking.linker import EntityLinker
from ..models import NormalizedItem
from ..reporting.digest import DailyDigestBuilder
from ..runtime import RuntimePaths, display_path
from ..storage import JsonDocumentStore, JsonlItemStore, TextDocumentStore

ROOT = Path(__file__).resolve().parents[3]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the deterministic daily research digest")
    parser.add_argument("--date", dest="report_date", help="Digest period end date in YYYY-MM-DD")
    parser.add_argument("--work-root", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = RuntimePaths.resolve(args.work_root)
    taxonomy = load_taxonomy(
        ROOT / "config/taxonomy.yaml", ROOT / "config/schemas/taxonomy.schema.json"
    )
    venues = load_venues(ROOT / "config/venues.yaml", ROOT / "config/schemas/venues.schema.json")
    reporting = load_reporting(
        ROOT / "config/reporting.yaml",
        ROOT / "config/schemas/reporting.schema.json",
        {venue["priority"] for venue in venues["venues"]},
    )
    linking = load_linking(
        ROOT / "config/linking.yaml", ROOT / "config/schemas/linking.schema.json"
    )
    report_date = parse_report_date(args.report_date, reporting["timezone"])

    items = JsonlItemStore(paths.items).load_items()
    link_result = EntityLinker(linking).link(items, generated_at=deterministic_link_time(items))
    JsonDocumentStore(paths.entities / "links.json").save(link_result.to_dict())

    digest = DailyDigestBuilder(reporting, taxonomy, venues).build(
        items, link_result, report_date=report_date
    )
    date_text = report_date.isoformat()
    JsonDocumentStore(paths.ranking / f"{date_text}.json").save(digest.ranking_document())
    TextDocumentStore(paths.daily_reports / f"{date_text}.md").save(digest.markdown)

    print(
        json.dumps(
            {
                "report_date": date_text,
                "ranked_items": len(digest.ranked),
                "links": len(link_result.edges),
                "report": display_path(paths.daily_reports / f"{date_text}.md"),
            },
            sort_keys=True,
        )
    )
    return 0


def parse_report_date(value: str | None, timezone_name: str) -> date:
    if value:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise SystemExit("--date must use YYYY-MM-DD") from exc
    return datetime.now(ZoneInfo(timezone_name)).date()


def deterministic_link_time(items: list[NormalizedItem]) -> str:
    if not items:
        return "1970-01-01T00:00:00Z"
    return max(item.discovered_at for item in items)


if __name__ == "__main__":
    raise SystemExit(main())
