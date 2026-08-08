from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..analytics.archive import build_archive_index
from ..analytics.trends import LongTermAnalyzer
from ..config import load_analytics, load_linking, load_reporting, load_taxonomy, load_venues
from ..linking.linker import EntityLinker
from ..models import parse_iso8601
from ..reporting.digest import report_window
from ..storage import JsonDocumentStore, JsonlItemStore, TextDocumentStore


ROOT = Path(__file__).resolve().parents[3]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build long-term research analytics and archive index")
    parser.add_argument("--date", dest="report_date", help="Analysis period end date in YYYY-MM-DD")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    taxonomy = load_taxonomy(ROOT / "config/taxonomy.yaml", ROOT / "config/schemas/taxonomy.schema.json")
    venues = load_venues(ROOT / "config/venues.yaml", ROOT / "config/schemas/venues.schema.json")
    reporting = load_reporting(
        ROOT / "config/reporting.yaml",
        ROOT / "config/schemas/reporting.schema.json",
        {venue["priority"] for venue in venues["venues"]},
    )
    analytics = load_analytics(
        ROOT / "config/analytics.yaml",
        ROOT / "config/schemas/analytics.schema.json",
    )
    linking = load_linking(ROOT / "config/linking.yaml", ROOT / "config/schemas/linking.schema.json")
    report_date = parse_report_date(args.report_date, reporting["timezone"])

    all_items = JsonlItemStore(ROOT / "data/items").load_items()
    _, cutoff = report_window(report_date, ZoneInfo(reporting["timezone"]), int(reporting["day_boundary_hour"]))
    items = [
        item
        for item in all_items
        if (timestamp := parse_iso8601(item.discovered_at)) is not None and timestamp < cutoff
    ]
    links = EntityLinker(linking).link(items, generated_at=deterministic_link_time(items))
    analyzer = LongTermAnalyzer(analytics, reporting, taxonomy)
    snapshot = analyzer.build(items, links, report_date=report_date)
    topic_labels = {topic["id"]: topic["label"] for topic in taxonomy["topics"]}

    date_text = report_date.isoformat()
    JsonDocumentStore(ROOT / f"data/analytics/{date_text}.json").save(snapshot.to_dict())
    TextDocumentStore(ROOT / f"reports/trends/{date_text}.md").save(analyzer.render_markdown(snapshot, topic_labels))

    archive = build_archive_index(
        items,
        links,
        generated_for_date=date_text,
        cutoff=snapshot.window_end,
        maximum_summary_characters=int(analytics["archive"]["maximum_summary_characters"]),
    )
    archive_path = ROOT / "data/archive/index.json"
    existing = JsonDocumentStore(archive_path).load()
    if should_replace_archive(existing, report_date):
        JsonDocumentStore(archive_path).save(archive.to_dict())

    print(
        json.dumps(
            {
                "report_date": date_text,
                "daily_buckets": len(snapshot.daily),
                "recurring_entities": len(snapshot.recurring_entities),
                "archive_records": len(archive.records),
                "report": f"reports/trends/{date_text}.md",
            },
            sort_keys=True,
        )
    )
    return 0


def should_replace_archive(existing: dict, report_date: date) -> bool:
    current = existing.get("generated_for_date")
    if not isinstance(current, str):
        return True
    try:
        return report_date >= date.fromisoformat(current)
    except ValueError:
        return True


def parse_report_date(value: str | None, timezone_name: str) -> date:
    if value:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise SystemExit("--date must use YYYY-MM-DD") from exc
    return datetime.now(ZoneInfo(timezone_name)).date()


def deterministic_link_time(items) -> str:
    if not items:
        return "1970-01-01T00:00:00Z"
    return max(item.discovered_at for item in items)


if __name__ == "__main__":
    raise SystemExit(main())
