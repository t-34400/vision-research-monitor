from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class RepositoryResearchAssessment:
    score: float
    category: str
    signals: list[str]


def assess_repository_research_quality(
    repository: dict[str, Any],
    *,
    venue_hits: set[tuple[str, int, str]],
    config: dict[str, Any],
    readme: str | None = None,
) -> RepositoryResearchAssessment:
    identity_text = normalize_text(
        " ".join(
            [
                str(repository.get("full_name") or repository.get("name") or ""),
                str(repository.get("description") or ""),
                " ".join(repository.get("topics") or []),
            ]
        )
    )
    evidence_text = normalize_text(" ".join([identity_text, readme or ""]))
    homepage = str(repository.get("homepage") or "").strip()
    link_text = " ".join([homepage, str(repository.get("description") or ""), readme or ""])

    collection_terms = [normalize_text(value) for value in config["collection_terms"]]
    tutorial_terms = [normalize_text(value) for value in config["tutorial_terms"]]
    research_terms = [normalize_text(value) for value in config["research_terms"]]
    publication_hosts = [str(value).casefold() for value in config["publication_hosts"]]

    is_collection = any(
        term and contains_normalized(identity_text, term) for term in collection_terms
    )
    is_tutorial = any(term and contains_normalized(identity_text, term) for term in tutorial_terms)

    score = float(config["baseline_score"])
    signals: list[str] = ["baseline"]

    if any(term and contains_normalized(evidence_text, term) for term in research_terms):
        score += float(config["research_term_bonus"])
        signals.append("research_term")

    normalized_link_text = link_text.casefold()
    if any(host in normalized_link_text for host in publication_hosts):
        score += float(config["publication_link_bonus"])
        signals.append("publication_link")

    if venue_hits:
        score += float(config["venue_bonus"])
        signals.append("venue")

    if homepage:
        score += float(config["homepage_bonus"])
        signals.append("homepage")

    stars = int(repository.get("stargazers_count") or 0)
    for threshold, bonus in (
        (50, config["stars_50_bonus"]),
        (250, config["stars_250_bonus"]),
        (1000, config["stars_1000_bonus"]),
    ):
        if stars >= threshold:
            score += float(bonus)
            signals.append(f"stars_{threshold}")

    category = "candidate"
    if is_collection:
        score = min(score, float(config["collection_cap"]))
        category = "collection"
        signals.append("collection_cap")
    elif is_tutorial:
        score = min(score, float(config["tutorial_cap"]))
        category = "tutorial"
        signals.append("tutorial_cap")
    elif score >= float(config["research_candidate_score"]):
        category = "research"

    return RepositoryResearchAssessment(
        score=round(max(0.0, min(1.0, score)), 4),
        category=category,
        signals=signals,
    )


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def contains_normalized(text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text} "
