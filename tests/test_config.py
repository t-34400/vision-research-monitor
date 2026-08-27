from pathlib import Path

from vision_research_monitor.config import (
    load_academic,
    load_analytics,
    load_github_discovery,
    load_linking,
    load_reporting,
    load_sources,
    load_taxonomy,
    load_venues,
    load_watchlist,
)

ROOT = Path(__file__).resolve().parents[1]


def test_project_configuration_is_valid() -> None:
    taxonomy = load_taxonomy(
        ROOT / "config/taxonomy.yaml",
        ROOT / "config/schemas/taxonomy.schema.json",
    )
    topics = {topic["id"] for topic in taxonomy["topics"]}
    watchlist = load_watchlist(
        ROOT / "config/github_watchlist.yaml",
        ROOT / "config/schemas/watchlist.schema.json",
        topics,
    )

    assert len(topics) == 58
    venues = load_venues(
        ROOT / "config/venues.yaml",
        ROOT / "config/schemas/venues.schema.json",
    )

    assert watchlist["accounts"]
    assert watchlist["repositories"]
    assert len(venues["venues"]) == 15

    discovery = load_github_discovery(
        ROOT / "config/github_discovery.yaml",
        ROOT / "config/schemas/github-discovery.schema.json",
        topics,
        {venue["id"] for venue in venues["venues"]},
    )
    query_topics = {
        topic
        for family in discovery["query_families"]
        for query in family["queries"]
        for topic in query["topics"]
    }
    assert query_topics == topics

    academic = load_academic(
        ROOT / "config/academic.yaml",
        ROOT / "config/schemas/academic.schema.json",
        {venue["id"] for venue in venues["venues"]},
    )
    assert academic["arxiv"]["categories"] == ["cs.CV", "cs.RO"]
    assert len(academic["openreview"]["editions"]) == 8

    linking = load_linking(
        ROOT / "config/linking.yaml",
        ROOT / "config/schemas/linking.schema.json",
    )
    assert linking["matching"]["fuzzy_title"]["minimum_similarity"] == 0.94

    sources = load_sources(
        ROOT / "config/sources.yaml",
        ROOT / "config/schemas/sources.schema.json",
        {venue["id"] for venue in venues["venues"]},
    )
    assert len(sources["cvf"]["editions"]) == 3
    assert sources["cvf"]["inventory_loss_guard"] == {
        "maximum_fraction": 0.05,
        "minimum_tolerance": 5,
    }
    assert len(sources["huggingface"]["queries"]) == 20
    assert len(sources["research_blogs"]["feeds"]) == 3

    reporting = load_reporting(
        ROOT / "config/reporting.yaml",
        ROOT / "config/schemas/reporting.schema.json",
        {venue["priority"] for venue in venues["venues"]},
    )
    assert reporting["timezone"] == "Asia/Tokyo"

    analytics = load_analytics(
        ROOT / "config/analytics.yaml",
        ROOT / "config/schemas/analytics.schema.json",
    )
    assert analytics["trend_windows_days"] == [7, 30]
