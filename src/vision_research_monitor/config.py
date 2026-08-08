from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


class ConfigError(ValueError):
    pass


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError(f"Configuration root must be an object: {path}")
    return data


def _validate_schema(data: dict[str, Any], schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda error: list(error.path))
    if errors:
        details = "; ".join(error.message for error in errors[:5])
        raise ConfigError(f"Schema validation failed for {schema_path.name}: {details}")


def load_taxonomy(path: Path, schema_path: Path) -> dict[str, Any]:
    data = _load_yaml(path)
    _validate_schema(data, schema_path)

    group_ids = [group["id"] for group in data["groups"]]
    topic_ids = [topic["id"] for topic in data["topics"]]
    if len(group_ids) != len(set(group_ids)):
        raise ConfigError("Taxonomy group IDs must be unique")
    if len(topic_ids) != len(set(topic_ids)):
        raise ConfigError("Taxonomy topic IDs must be unique")

    groups = set(group_ids)
    unknown_groups = sorted({topic["group"] for topic in data["topics"]} - groups)
    if unknown_groups:
        raise ConfigError(f"Unknown taxonomy groups: {', '.join(unknown_groups)}")
    return data


def load_watchlist(path: Path, schema_path: Path, topic_ids: set[str]) -> dict[str, Any]:
    data = _load_yaml(path)
    _validate_schema(data, schema_path)

    logins = [account["login"].lower() for account in data["accounts"]]
    repos = [repository["repo"].lower() for repository in data["repositories"]]
    if len(logins) != len(set(logins)):
        raise ConfigError("GitHub watch account logins must be unique")
    if len(repos) != len(set(repos)):
        raise ConfigError("GitHub watch repository names must be unique")

    for repository in data["repositories"]:
        unknown = sorted(set(repository.get("topics", [])) - topic_ids)
        if unknown:
            raise ConfigError(f"Unknown topics for {repository['repo']}: {', '.join(unknown)}")
    return data


def load_venues(path: Path, schema_path: Path) -> dict[str, Any]:
    data = _load_yaml(path)
    _validate_schema(data, schema_path)
    venue_ids = [venue["id"] for venue in data["venues"]]
    if len(venue_ids) != len(set(venue_ids)):
        raise ConfigError("Academic venue IDs must be unique")
    return data


def load_github_discovery(
    path: Path,
    schema_path: Path,
    topic_ids: set[str],
    venue_ids: set[str],
) -> dict[str, Any]:
    data = _load_yaml(path)
    _validate_schema(data, schema_path)

    family_ids = [family["id"] for family in data["query_families"]]
    if len(family_ids) != len(set(family_ids)):
        raise ConfigError("GitHub discovery query family IDs must be unique")

    query_ids: list[str] = []
    covered_topics: set[str] = set()
    for family in data["query_families"]:
        for query in family["queries"]:
            query_ids.append(query["id"])
            unknown = sorted(set(query["topics"]) - topic_ids)
            if unknown:
                raise ConfigError(f"Unknown discovery topics for {query['id']}: {', '.join(unknown)}")
            covered_topics.update(query["topics"])

    if len(query_ids) != len(set(query_ids)):
        raise ConfigError("GitHub discovery query IDs must be unique")

    uncovered = sorted(topic_ids - covered_topics)
    if uncovered:
        raise ConfigError(f"Taxonomy topics missing discovery queries: {', '.join(uncovered)}")

    configured_venues = set(data["venue_search"].get("venue_ids", []))
    unknown_venues = sorted(configured_venues - venue_ids)
    if unknown_venues:
        raise ConfigError(f"Unknown discovery venues: {', '.join(unknown_venues)}")
    return data


def load_academic(
    path: Path,
    schema_path: Path,
    venue_ids: set[str],
) -> dict[str, Any]:
    data = _load_yaml(path)
    _validate_schema(data, schema_path)

    editions = data["openreview"]["editions"]
    openreview_ids = [edition["venue_id"] for edition in editions]
    if len(openreview_ids) != len(set(openreview_ids)):
        raise ConfigError("OpenReview venue edition IDs must be unique")

    unknown_venues = sorted({edition["venue"] for edition in editions} - venue_ids)
    if unknown_venues:
        raise ConfigError(f"Unknown academic venues: {', '.join(unknown_venues)}")

    if data["window"]["initial_lookback_hours"] > data["window"]["max_catchup_hours"]:
        raise ConfigError("Academic initial lookback cannot exceed maximum catch-up window")
    return data


def load_linking(path: Path, schema_path: Path) -> dict[str, Any]:
    data = _load_yaml(path)
    _validate_schema(data, schema_path)

    exact = data["matching"]["exact_title"]
    fuzzy = data["matching"]["fuzzy_title"]
    if exact["minimum_author_overlap"] < 0 or fuzzy["minimum_author_overlap"] < 0:
        raise ConfigError("Linking author-overlap thresholds must be non-negative")
    if fuzzy["minimum_similarity"] <= 0:
        raise ConfigError("Linking fuzzy-title similarity must be positive")
    return data


def load_semantic(path: Path, schema_path: Path, topic_ids: set[str]) -> dict[str, Any]:
    data = _load_yaml(path)
    _validate_schema(data, schema_path)

    profile_topics = [profile["topic"] for profile in data["profiles"]]
    if len(profile_topics) != len(set(profile_topics)):
        raise ConfigError("Semantic topic profile IDs must be unique")
    unknown = sorted(set(profile_topics) - topic_ids)
    missing = sorted(topic_ids - set(profile_topics))
    if unknown:
        raise ConfigError(f"Unknown semantic topic profiles: {', '.join(unknown)}")
    if missing:
        raise ConfigError(f"Semantic profiles missing taxonomy topics: {', '.join(missing)}")

    model = data["model"]
    if model["word_ngram_min"] > model["word_ngram_max"]:
        raise ConfigError("Semantic word n-gram minimum cannot exceed maximum")
    if model["char_ngram_min"] > model["char_ngram_max"]:
        raise ConfigError("Semantic character n-gram minimum cannot exceed maximum")
    if float(model["word_weight"]) + float(model["char_weight"]) <= 0:
        raise ConfigError("Semantic feature weights must have positive total weight")

    classification = data["classification"]
    if classification["acceptance_similarity"] < classification["minimum_topic_similarity"]:
        raise ConfigError("Semantic acceptance similarity cannot be below topic selection threshold")
    llm = data["llm"]
    if llm["minimum_semantic_score"] > llm["maximum_semantic_score"]:
        raise ConfigError("Semantic LLM minimum score cannot exceed maximum score")
    return data

def load_reporting(path: Path, schema_path: Path, venue_priorities: set[str]) -> dict[str, Any]:
    data = _load_yaml(path)
    _validate_schema(data, schema_path)

    weights = data["ranking"]["weights"]
    total_weight = sum(float(value) for value in weights.values())
    if total_weight <= 0:
        raise ConfigError("Ranking weights must sum to a positive value")

    unknown_priorities = sorted(set(data["ranking"]["venue_priority"]) - venue_priorities)
    if unknown_priorities:
        raise ConfigError(f"Unknown venue priority classes: {', '.join(unknown_priorities)}")
    return data
