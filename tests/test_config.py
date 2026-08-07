from pathlib import Path

from vision_research_monitor.config import load_taxonomy, load_venues, load_watchlist


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
