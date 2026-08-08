from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from vision_research_monitor.linking.linker import EntityLinker
from vision_research_monitor.models import NormalizedItem
from vision_research_monitor.reporting.digest import DailyDigestBuilder, report_window
from vision_research_monitor.reporting.ranking import ResearchRanker, change_label


ROOT = Path(__file__).resolve().parents[1]


def load_inputs() -> tuple[dict, dict, dict, dict]:
    reporting = yaml.safe_load((ROOT / "config/reporting.yaml").read_text())
    taxonomy = yaml.safe_load((ROOT / "config/taxonomy.yaml").read_text())
    venues = yaml.safe_load((ROOT / "config/venues.yaml").read_text())
    linking = yaml.safe_load((ROOT / "config/linking.yaml").read_text())
    return reporting, taxonomy, venues, linking


def make_item(item_id: str, **overrides) -> NormalizedItem:
    values = {
        "id": item_id,
        "source": "github",
        "source_id": item_id.rsplit(":", 1)[-1],
        "kind": "repository",
        "title": "example/research-project",
        "url": "https://github.com/example/research-project",
        "discovered_at": "2026-08-08T00:00:00Z",
        "published_at": "2026-08-08T00:00:00Z",
        "topics": ["gaussian_splatting"],
        "priority": {},
        "scores": {"relevance": 0.8},
        "metadata": {"action": "discovered", "stars_delta": 25},
    }
    values.update(overrides)
    return NormalizedItem(**values)


def test_ranking_keeps_signals_separate_and_watch_override() -> None:
    reporting, _, venues, _ = load_inputs()
    venue_priorities = {venue["id"]: venue["priority"] for venue in venues["venues"]}
    ranker = ResearchRanker(reporting, venue_priorities)
    item = make_item(
        "github:event:101",
        kind="event",
        priority={"source": 1.0},
        scores={"relevance": 0.0},
        metadata={"action": "metadata_updated", "stars_delta": 0},
    )

    ranked = ranker.rank(item, reference_time=datetime(2026, 8, 8, 23, tzinfo=timezone.utc))

    assert ranked.signals.priority == 1.0
    assert ranked.signals.relevance == 0.0
    assert ranked.watched_override is True
    assert ranker.included(ranked) is True


def test_popularity_delta_is_log_scaled() -> None:
    reporting, _, venues, _ = load_inputs()
    venue_priorities = {venue["id"]: venue["priority"] for venue in venues["venues"]}
    ranker = ResearchRanker(reporting, venue_priorities)
    low = ranker.rank(make_item("github:repository:1", metadata={"action": "discovered", "stars_delta": 1}), reference_time=datetime(2026, 8, 8, 23, tzinfo=timezone.utc))
    high = ranker.rank(make_item("github:repository:2", metadata={"action": "discovered", "stars_delta": 100}), reference_time=datetime(2026, 8, 8, 23, tzinfo=timezone.utc))

    assert 0 < low.signals.popularity < high.signals.popularity
    assert high.signals.popularity == 1.0



def test_repository_freshness_uses_activity_time() -> None:
    reporting, _, venues, _ = load_inputs()
    venue_priorities = {venue["id"]: venue["priority"] for venue in venues["venues"]}
    ranker = ResearchRanker(reporting, venue_priorities)
    item = make_item(
        "github:repository:old-active",
        published_at="2020-01-01T00:00:00Z",
        updated_at="2026-08-08T22:00:00Z",
    )

    ranked = ranker.rank(item, reference_time=datetime(2026, 8, 8, 23, tzinfo=timezone.utc))

    assert ranked.signals.freshness > 0.98


def test_change_labels_cover_acceptance_release_and_new_items() -> None:
    accepted = make_item(
        "openreview:event:a",
        source="openreview",
        source_id="a:status:submitted:accepted:1",
        kind="event",
        metadata={"action": "status_changed", "status": "accepted"},
    )
    release = make_item("github:release:1", kind="release", metadata={"action": "released"})
    paper = make_item("arxiv:paper:1", source="arxiv", source_id="1", kind="paper")

    assert change_label(accepted) == "ACCEPTED"
    assert change_label(release) == "RELEASED"
    assert change_label(paper) == "NEW"


def test_daily_digest_uses_fixed_jst_window_and_deduplicates_linked_papers() -> None:
    reporting, taxonomy, venues, linking = load_inputs()
    arxiv = make_item(
        "arxiv:paper:2608.00001",
        source="arxiv",
        source_id="2608.00001",
        kind="paper",
        title="Sparse View Gaussian Reconstruction",
        url="https://arxiv.org/abs/2608.00001",
        discovered_at="2026-08-07T23:00:00Z",
        published_at="2026-08-07T22:00:00Z",
        authors=["Alice Example"],
        venue=None,
        metadata={"doi": "10.1000/test"},
    )
    openreview = make_item(
        "openreview:paper:abc123",
        source="openreview",
        source_id="abc123",
        kind="paper",
        title="Sparse View Gaussian Reconstruction",
        url="https://openreview.net/forum?id=abc123",
        discovered_at="2026-08-07T23:10:00Z",
        published_at="2026-08-07T22:00:00Z",
        authors=["Alice Example"],
        venue="cvpr",
        metadata={"status": "accepted", "venue_year": 2026, "doi": "10.1000/test"},
    )
    watched = make_item(
        "github:commit:101:commit:sha",
        source_id="101:commit:sha",
        kind="commit",
        title="nerfstudio-project/gsplat default branch advanced",
        discovered_at="2026-08-07T23:20:00Z",
        published_at="2026-08-07T23:15:00Z",
        priority={"source": 1.0},
        metadata={"action": "default_branch_advanced", "stars_delta": 3},
    )
    items = [arxiv, openreview, watched]
    links = EntityLinker(linking).link(items, generated_at="2026-08-07T23:20:00Z")

    result = DailyDigestBuilder(reporting, taxonomy, venues).build(items, links, report_date=date(2026, 8, 9))

    start, end = report_window(date(2026, 8, 9), DailyDigestBuilder(reporting, taxonomy, venues).timezone, 8)
    assert start.isoformat() == "2026-08-07T23:00:00+00:00"
    assert end.isoformat() == "2026-08-08T23:00:00+00:00"
    assert result.markdown.count("Sparse View Gaussian Reconstruction") == 1
    assert "## Priority Watch" in result.markdown
    assert "## Accepted Papers" in result.markdown
    assert "[UPDATED]" in result.markdown
