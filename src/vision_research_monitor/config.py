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
