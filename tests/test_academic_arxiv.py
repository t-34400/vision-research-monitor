import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from vision_research_monitor.academic.arxiv import ArxivCollector, parse_arxiv_feed
from vision_research_monitor.academic.common import AcademicCoverageError
from vision_research_monitor.academic.http import AcademicHttpClient


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/academic"


def load_inputs() -> tuple[dict, dict, dict]:
    return (
        yaml.safe_load((ROOT / "config/academic.yaml").read_text()),
        yaml.safe_load((ROOT / "config/taxonomy.yaml").read_text()),
        yaml.safe_load((ROOT / "config/venues.yaml").read_text()),
    )


def test_parse_arxiv_feed_preserves_source_metadata() -> None:
    papers, total = parse_arxiv_feed((FIXTURES / "arxiv_feed.xml").read_text())

    assert total == 2
    assert papers[0].source_id == "2608.01234"
    assert papers[0].versioned_id == "2608.01234v2"
    assert papers[0].primary_category == "cs.CV"
    assert papers[0].authors == ["Alice Example", "Bob Example"]
    assert papers[0].pdf_url == "https://arxiv.org/pdf/2608.01234v2"


def test_arxiv_collector_filters_and_normalizes_relevant_papers() -> None:
    config, taxonomy, venues = load_inputs()
    feed = (FIXTURES / "arxiv_feed.xml").read_text()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=feed, headers={"content-type": "application/atom+xml"})

    with AcademicHttpClient(
        config["arxiv"]["base_url"],
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    ) as client:
        collector = ArxivCollector(
            client,
            {},
            config,
            taxonomy,
            venues,
            sleeper=lambda _: None,
            monotonic=lambda: 0.0,
        )
        result = collector.collect(datetime(2026, 8, 8, tzinfo=timezone.utc))

    assert result.failed_targets == 0
    assert len(result.items) == 1
    item = result.items[0]
    assert item.id == "arxiv:paper:2608.01234"
    assert item.venue == "eccv"
    assert "gaussian_splatting" in item.topics
    assert item.scores["relevance"] >= config["matching"]["minimum_relevance_score"]
    assert len(requests) == 2
    assert all("submittedDate" in request.url.params["search_query"] for request in requests)


def test_arxiv_stale_checkpoint_requires_explicit_backfill() -> None:
    config, taxonomy, venues = load_inputs()
    state = {"academic": {"arxiv": {"last_successful_at": "2026-08-01T00:00:00Z"}}}
    with AcademicHttpClient(config["arxiv"]["base_url"], transport=httpx.MockTransport(lambda _: httpx.Response(500))) as client:
        collector = ArxivCollector(client, state, config, taxonomy, venues)
        try:
            collector.collection_window(datetime(2026, 8, 8, tzinfo=timezone.utc))
        except AcademicCoverageError as exc:
            assert "maximum automatic catch-up" in str(exc)
        else:
            raise AssertionError("Expected stale checkpoint coverage failure")
