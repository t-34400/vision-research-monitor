from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from ..models import NormalizedItem, parse_iso8601, to_iso8601


def normalize_registry(registry: dict[str, Any]) -> dict[str, Any]:
    registry.setdefault("version", 1)
    if registry["version"] != 1:
        raise ValueError("Unsupported GitHub auto-watch registry version")
    registry.setdefault("repositories", {})
    return registry


def update_auto_watch_registry(
    registry: dict[str, Any],
    items: list[NormalizedItem],
    config: dict[str, Any],
    run_at: datetime,
) -> dict[str, int]:
    normalize_registry(registry)
    if not config.get("enabled", True):
        return {"eligible": 0, "promoted": 0, "tracked": len(registry["repositories"])}

    repositories: dict[str, dict[str, Any]] = registry["repositories"]
    eligible = 0
    promoted = 0
    observed_at = to_iso8601(run_at.astimezone(UTC))

    for item in items:
        if item.source != "github" or item.kind != "repository":
            continue
        if not auto_watch_eligible(item, config):
            continue
        eligible += 1
        repo_id = item.source_id
        previous = repositories.get(repo_id)
        repositories[repo_id] = registry_entry(item, previous, observed_at, config)
        if previous is None:
            promoted += 1

    limit = int(config["max_repositories"])
    if len(repositories) > limit:
        retained = sorted(
            repositories.items(),
            key=lambda pair: registry_rank(pair[1]),
            reverse=True,
        )[:limit]
        registry["repositories"] = dict(retained)

    registry["last_updated_at"] = observed_at
    return {
        "eligible": eligible,
        "promoted": promoted,
        "tracked": len(registry["repositories"]),
    }


def auto_watch_eligible(item: NormalizedItem, config: dict[str, Any]) -> bool:
    metadata = item.metadata
    if metadata.get("fork") or metadata.get("archived"):
        return False
    research_quality = metadata.get("research_quality")
    if isinstance(research_quality, dict) and research_quality.get("category") in {
        "collection",
        "tutorial",
    }:
        return False

    stars = numeric_int(metadata.get("stars"))
    research = numeric_float(item.scores.get("research_relevance"))
    if stars >= int(config["established_minimum_stars"]):
        return True
    if research >= float(config["research_minimum_score"]) and stars >= int(
        config["research_minimum_stars"]
    ):
        return True
    return research >= float(config["strong_research_minimum_score"]) and stars >= int(
        config["strong_research_minimum_stars"]
    )


def registry_entry(
    item: NormalizedItem,
    previous: dict[str, Any] | None,
    observed_at: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    metadata = item.metadata
    research_quality = metadata.get("research_quality")
    category = research_quality.get("category") if isinstance(research_quality, dict) else None
    stars = numeric_int(metadata.get("stars"))
    research = numeric_float(item.scores.get("research_relevance"))
    first_promoted_at = (
        previous.get("first_promoted_at") if isinstance(previous, dict) else None
    ) or observed_at
    return {
        "repo_id": item.source_id,
        "full_name": item.title,
        "url": item.url,
        "topics": sorted(set(item.topics)),
        "priority": "normal",
        "first_promoted_at": first_promoted_at,
        "last_observed_at": observed_at,
        "stars": stars,
        "research_relevance": research,
        "research_category": category,
        "promotion_reasons": promotion_reasons(stars, research, config),
    }


def promotion_reasons(stars: int, research: float, config: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if stars >= int(config["established_minimum_stars"]):
        reasons.append("established")
    if research >= float(config["research_minimum_score"]) and stars >= int(
        config["research_minimum_stars"]
    ):
        reasons.append("research_tool")
    if research >= float(config["strong_research_minimum_score"]) and stars >= int(
        config["strong_research_minimum_stars"]
    ):
        reasons.append("strong_research")
    return reasons


def registry_rank(entry: dict[str, Any]) -> tuple[float, float, float, float]:
    reasons = set(entry.get("promotion_reasons") or [])
    tier = 3.0 if "established" in reasons else 2.0 if "strong_research" in reasons else 1.0
    research = numeric_float(entry.get("research_relevance"))
    stars = numeric_int(entry.get("stars"))
    recency = parse_iso8601(entry.get("last_observed_at"))
    timestamp = recency.timestamp() if recency is not None else 0.0
    return tier, research, math.log1p(stars), timestamp


def registry_repository_configs(registry: dict[str, Any]) -> list[dict[str, Any]]:
    normalize_registry(registry)
    configs: list[dict[str, Any]] = []
    for entry in registry["repositories"].values():
        full_name = entry.get("full_name")
        if not isinstance(full_name, str) or "/" not in full_name:
            continue
        configs.append(
            {
                "repo": full_name,
                "repo_id": str(entry.get("repo_id") or ""),
                "priority": entry.get("priority", "normal"),
                "topics": list(entry.get("topics") or []),
                "auto_watch": True,
            }
        )
    return configs


def numeric_int(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def numeric_float(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0
