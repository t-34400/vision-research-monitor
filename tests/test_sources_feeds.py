from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

from vision_research_monitor.http import HttpClient
from vision_research_monitor.sources.feeds import ResearchFeedCollector, parse_feed

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/sources"


def load_inputs() -> tuple[dict, dict]:
    config = yaml.safe_load((ROOT / "config/sources.yaml").read_text())
    config["research_blogs"]["feeds"] = [
        {
            "id": "example-research",
            "name": "Example Research",
            "organization": "Example Research",
            "url": "https://research.example.org/feed.xml",
            "priority": 0.7,
        }
    ]
    taxonomy = yaml.safe_load((ROOT / "config/taxonomy.yaml").read_text())
    return config, taxonomy


def test_feed_parser_supports_rss_and_atom() -> None:
    rss = parse_feed((FIXTURES / "research_feed.xml").read_text())
    atom = parse_feed((FIXTURES / "research_atom.xml").read_text())
    assert rss[0].authors == ["Research Team"]
    assert rss[0].published_at == datetime(2026, 8, 8, 5, tzinfo=UTC)
    assert atom[0].title == "Fast Gaussian Splatting for Novel View Synthesis"
    assert atom[0].authors == ["Alice Example"]


def test_atom_parser_preserves_word_boundaries_across_inline_elements() -> None:
    atom = parse_feed(
        """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>alignment</id>
    <title>Understanding <em>Multimodal</em><strong>LLMs</strong>: A Study</title>
    <link rel="alternate" href="https://research.example.org/alignment" />
    <published>2026-08-08T03:00:00Z</published>
    <summary>Similar to <em>language</em><strong>models</strong>, those<strong>features</strong> matter.</summary>
  </entry>
</feed>
"""
    )

    assert atom[0].title == "Understanding Multimodal LLMs: A Study"
    assert atom[0].summary == "Similar to language models, those features matter."


def test_research_feed_collector_filters_irrelevant_posts() -> None:
    config, taxonomy = load_inputs()
    feed = (FIXTURES / "research_feed.xml").read_text()
    with HttpClient(
        "https://research.example.org",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=feed)),
        sleeper=lambda _: None,
    ) as client:
        result = ResearchFeedCollector(client, {}, config, taxonomy).collect(
            datetime(2026, 8, 8, 8, tzinfo=UTC),
            window_start=datetime(2026, 8, 8, 0, tzinfo=UTC),
            window_end=datetime(2026, 8, 8, 8, tzinfo=UTC),
        )

    assert result.failed_targets == 0
    assert len(result.items) == 1
    item = result.items[0]
    assert item.kind == "article"
    assert item.organization == "Example Research"
    assert {"monocular_depth", "metric_depth"}.issubset(item.topics)
