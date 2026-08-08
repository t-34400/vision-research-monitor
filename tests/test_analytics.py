from __future__ import annotations

from datetime import date, datetime, timezone

from vision_research_monitor.analytics.archive import build_archive_index, search_archive
from vision_research_monitor.analytics.trends import LongTermAnalyzer, activity_date
from vision_research_monitor.linking.linker import EntityLinkResult
from vision_research_monitor.models import NormalizedItem


def make_item(
    item_id: str,
    *,
    source: str = "arxiv",
    kind: str = "paper",
    discovered_at: str,
    title: str | None = None,
    topics: list[str] | None = None,
    metadata: dict | None = None,
) -> NormalizedItem:
    return NormalizedItem(
        id=item_id,
        source=source,
        source_id=item_id,
        kind=kind,
        title=title or item_id,
        url=f"https://example.org/{item_id}",
        discovered_at=discovered_at,
        topics=topics or [],
        metadata=metadata or {},
    )


def analytics_config() -> dict:
    return {
        "version": 1,
        "history_days": 60,
        "trend_windows_days": [7, 30],
        "momentum": {
            "smoothing": 1.0,
            "minimum_current_entities": 1,
            "top_topics_per_window": 10,
        },
        "growth": {"primary_window_days": 7},
        "recurring_entities": {
            "lookback_days": 30,
            "minimum_activity_items": 2,
            "minimum_active_days": 2,
            "limit": 10,
        },
        "archive": {
            "maximum_summary_characters": 100,
            "default_search_limit": 20,
            "maximum_search_limit": 100,
        },
    }


def reporting_config() -> dict:
    return {"timezone": "Asia/Tokyo", "day_boundary_hour": 8}


def taxonomy() -> dict:
    return {
        "topics": [
            {"id": "depth", "label": "Depth"},
            {"id": "slam", "label": "SLAM"},
        ]
    }


def empty_links() -> EntityLinkResult:
    return EntityLinkResult("2026-08-08T00:00:00Z", [], {}, {})


def test_activity_date_uses_same_0800_jst_boundary_as_digest() -> None:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Tokyo")
    before = datetime(2026, 8, 7, 22, 59, tzinfo=timezone.utc)
    boundary = datetime(2026, 8, 7, 23, 0, tzinfo=timezone.utc)

    assert activity_date(before, tz, 8) == date(2026, 8, 8)
    assert activity_date(boundary, tz, 8) == date(2026, 8, 9)


def test_daily_counts_dedupe_linked_papers_and_preserve_raw_item_volume() -> None:
    items = [
        make_item("arxiv:1", discovered_at="2026-08-08T01:00:00Z", topics=["depth"]),
        make_item("openreview:1", source="openreview", discovered_at="2026-08-08T02:00:00Z", topics=["depth"]),
        make_item(
            "github:repository:7",
            source="github",
            kind="repository",
            discovered_at="2026-08-08T03:00:00Z",
            topics=["slam"],
        ),
    ]
    links = EntityLinkResult(
        "2026-08-08T03:00:00Z",
        [],
        {"entity:paper": ["arxiv:1", "openreview:1"]},
        {},
    )
    snapshot = LongTermAnalyzer(analytics_config(), reporting_config(), taxonomy()).build(
        items,
        links,
        report_date=date(2026, 8, 9),
    )

    bucket = snapshot.daily[-1]
    assert bucket["items"] == 3
    assert bucket["entities"] == 2
    assert bucket["topics"] == {"depth": 1, "slam": 1}
    assert bucket["new_papers"] == 1
    assert bucket["new_repositories"] == 1


def test_topic_momentum_compares_unique_entity_share_between_windows() -> None:
    items = []
    for index in range(4):
        items.append(
            make_item(
                f"current-depth-{index}",
                discovered_at=f"2026-08-0{8 - index}T01:00:00Z",
                topics=["depth"],
            )
        )
    for index in range(2):
        items.append(
            make_item(
                f"current-slam-{index}",
                discovered_at=f"2026-08-0{8 - index}T02:00:00Z",
                topics=["slam"],
            )
        )
    items.extend(
        [
            make_item("previous-depth", discovered_at="2026-07-30T01:00:00Z", topics=["depth"]),
            make_item("previous-slam-1", discovered_at="2026-07-30T02:00:00Z", topics=["slam"]),
            make_item("previous-slam-2", discovered_at="2026-07-29T02:00:00Z", topics=["slam"]),
            make_item("previous-slam-3", discovered_at="2026-07-28T02:00:00Z", topics=["slam"]),
        ]
    )

    snapshot = LongTermAnalyzer(analytics_config(), reporting_config(), taxonomy()).build(
        items,
        empty_links(),
        report_date=date(2026, 8, 9),
    )
    seven_day = {entry.topic: entry for entry in snapshot.topic_momentum[7]}

    assert seven_day["depth"].current_entities == 4
    assert seven_day["depth"].previous_entities == 1
    assert seven_day["depth"].momentum_score > 0
    assert seven_day["slam"].momentum_score < 0


def test_growth_counts_first_seen_linked_entities_once() -> None:
    items = [
        make_item("arxiv:new", discovered_at="2026-08-05T01:00:00Z", topics=["depth"]),
        make_item("openreview:new", source="openreview", discovered_at="2026-08-06T01:00:00Z", topics=["depth"]),
        make_item("arxiv:old", discovered_at="2026-07-29T01:00:00Z", topics=["depth"]),
        make_item(
            "github:repository:new",
            source="github",
            kind="repository",
            discovered_at="2026-08-04T01:00:00Z",
            topics=["slam"],
        ),
    ]
    links = EntityLinkResult(
        "2026-08-08T00:00:00Z",
        [],
        {"entity:new-paper": ["arxiv:new", "openreview:new"]},
        {},
    )
    snapshot = LongTermAnalyzer(analytics_config(), reporting_config(), taxonomy()).build(
        items,
        links,
        report_date=date(2026, 8, 9),
    )

    assert snapshot.paper_growth.current == 1
    assert snapshot.paper_growth.previous == 1
    assert snapshot.repository_growth.current == 1
    assert snapshot.repository_growth.previous == 0
    assert snapshot.repository_growth.growth_percent is None


def test_recurring_entities_require_activity_on_multiple_days() -> None:
    items = [
        make_item(
            "github:repository:1",
            source="github",
            kind="repository",
            discovered_at="2026-08-02T01:00:00Z",
            title="Example SLAM",
            topics=["slam"],
        ),
        make_item(
            "github:commit:1:a",
            source="github",
            kind="commit",
            discovered_at="2026-08-05T01:00:00Z",
            title="Example SLAM updated",
            topics=["slam"],
        ),
        make_item(
            "github:release:1:b",
            source="github",
            kind="release",
            discovered_at="2026-08-07T01:00:00Z",
            title="Example SLAM v2",
            topics=["slam"],
        ),
    ]
    links = EntityLinkResult(
        "2026-08-08T00:00:00Z",
        [],
        {"entity:repo": [item.id for item in items]},
        {},
    )
    config = analytics_config()
    config["recurring_entities"]["minimum_activity_items"] = 3
    snapshot = LongTermAnalyzer(config, reporting_config(), taxonomy()).build(
        items,
        links,
        report_date=date(2026, 8, 9),
    )

    assert len(snapshot.recurring_entities) == 1
    recurring = snapshot.recurring_entities[0]
    assert recurring.entity_id == "entity:repo"
    assert recurring.title == "Example SLAM"
    assert recurring.active_days == 3


def test_archive_search_supports_text_and_structured_filters() -> None:
    visible = make_item(
        "paper:visible",
        source="arxiv",
        discovered_at="2026-08-07T01:00:00Z",
        title="Metric Depth from a Single Image",
        topics=["depth"],
    )
    visible.summary = "Predict absolute scene distance from monocular RGB input."
    hidden = make_item(
        "project:hidden",
        source="cvf",
        kind="project",
        discovered_at="2026-08-07T02:00:00Z",
        title="Metric Depth Project",
        topics=["depth"],
        metadata={"reportable": False},
    )
    index = build_archive_index(
        [visible, hidden],
        empty_links(),
        generated_for_date="2026-08-09",
        cutoff=datetime(2026, 8, 8, 23, tzinfo=timezone.utc),
        maximum_summary_characters=100,
    )

    results = search_archive(index, query="metric depth", topics={"depth"}, kinds={"paper"}, limit=10)
    assert [record.id for record in results] == ["paper:visible"]
    assert search_archive(index, query="project", limit=10) == []
    assert [record.id for record in search_archive(index, query="project", include_hidden=True, limit=10)] == [
        "project:hidden"
    ]


def test_hidden_relationship_records_do_not_inflate_trend_activity() -> None:
    visible = make_item(
        "paper:1",
        discovered_at="2026-08-08T01:00:00Z",
        topics=["depth"],
    )
    hidden = make_item(
        "project:1",
        source="cvf",
        kind="project",
        discovered_at="2026-08-08T02:00:00Z",
        topics=["depth"],
        metadata={"reportable": False},
    )
    links = EntityLinkResult(
        "2026-08-08T02:00:00Z",
        [],
        {"entity:paper": [visible.id, hidden.id]},
        {},
    )

    snapshot = LongTermAnalyzer(analytics_config(), reporting_config(), taxonomy()).build(
        [visible, hidden],
        links,
        report_date=date(2026, 8, 9),
    )

    bucket = snapshot.daily[-1]
    assert bucket["items"] == 1
    assert bucket["entities"] == 1
    assert bucket["topics"] == {"depth": 1}


def test_historical_build_does_not_replace_newer_archive() -> None:
    from vision_research_monitor.cli.build_trends import should_replace_archive

    assert should_replace_archive({"generated_for_date": "2026-08-09"}, date(2026, 8, 10))
    assert should_replace_archive({"generated_for_date": "2026-08-09"}, date(2026, 8, 9))
    assert not should_replace_archive({"generated_for_date": "2026-08-09"}, date(2026, 8, 8))
