from datetime import UTC, datetime

from vision_research_monitor.github.auto_watch import (
    auto_watch_eligible,
    registry_repository_configs,
    update_auto_watch_registry,
)
from vision_research_monitor.models import NormalizedItem


def config() -> dict[str, object]:
    return {
        "enabled": True,
        "max_repositories": 2,
        "established_minimum_stars": 1000,
        "research_minimum_score": 0.4,
        "research_minimum_stars": 100,
        "strong_research_minimum_score": 0.65,
        "strong_research_minimum_stars": 25,
    }


def repository_item(
    repo_id: int,
    *,
    stars: int,
    research: float,
    category: str = "research",
) -> NormalizedItem:
    return NormalizedItem(
        id=f"github:repository:{repo_id}",
        source="github",
        source_id=str(repo_id),
        kind="repository",
        title=f"example/tool-{repo_id}",
        url=f"https://github.com/example/tool-{repo_id}",
        discovered_at="2026-08-08T00:00:00Z",
        topics=["gaussian_splatting"],
        scores={"research_relevance": research},
        metadata={
            "stars": stars,
            "fork": False,
            "archived": False,
            "research_quality": {"category": category, "signals": []},
        },
    )


def test_auto_watch_accepts_established_or_research_tools_but_not_tutorials() -> None:
    cfg = config()

    assert auto_watch_eligible(repository_item(1, stars=1200, research=0.2), cfg)
    assert auto_watch_eligible(repository_item(2, stars=120, research=0.4), cfg)
    assert auto_watch_eligible(repository_item(3, stars=30, research=0.7), cfg)
    assert not auto_watch_eligible(repository_item(4, stars=99, research=0.4), cfg)
    assert not auto_watch_eligible(
        repository_item(5, stars=2000, research=0.8, category="tutorial"), cfg
    )


def test_registry_is_bounded_and_prefers_established_tools() -> None:
    registry: dict[str, object] = {}
    items = [
        repository_item(1, stars=150, research=0.7),
        repository_item(2, stars=5000, research=0.2, category="candidate"),
        repository_item(3, stars=200, research=0.8),
    ]

    summary = update_auto_watch_registry(
        registry,
        items,
        config(),
        datetime(2026, 8, 8, 1, tzinfo=UTC),
    )

    assert summary == {"eligible": 3, "promoted": 3, "tracked": 2}
    assert set(registry["repositories"]) == {"2", "3"}
    configs = registry_repository_configs(registry)
    assert {entry["repo"] for entry in configs} == {"example/tool-2", "example/tool-3"}
    assert all(entry["priority"] == "normal" for entry in configs)
