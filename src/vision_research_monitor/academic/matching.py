from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AcademicMatch:
    score: float
    topics: list[str]
    matched_terms: list[str]


class AcademicLexicalMatcher:
    def __init__(self, taxonomy: dict[str, Any], config: dict[str, Any]) -> None:
        self.title_weight = float(config["title_weight"])
        self.abstract_weight = float(config["abstract_weight"])
        self.keyword_weight = float(config["keyword_weight"])
        self._aliases: dict[str, list[tuple[str, str]]] = {}
        for topic in taxonomy["topics"]:
            aliases: list[tuple[str, str]] = []
            for alias in topic["aliases"]:
                normalized = normalize_text(alias)
                if normalized:
                    aliases.append((alias, normalized))
            self._aliases[topic["id"]] = aliases

    def match(self, title: str, abstract: str, *, keywords: list[str] | None = None) -> AcademicMatch:
        fields = {
            "title": normalize_text(title),
            "abstract": normalize_text(abstract),
            "keywords": normalize_text(" ".join(keywords or [])),
        }
        field_weights = {
            "title": self.title_weight,
            "abstract": self.abstract_weight,
            "keywords": self.keyword_weight,
        }
        topic_scores: dict[str, float] = {}
        matched_terms: set[str] = set()

        for topic_id, aliases in self._aliases.items():
            best = 0.0
            best_term: str | None = None
            for original, alias in aliases:
                for field_name, text in fields.items():
                    if contains_normalized(text, alias) and field_weights[field_name] > best:
                        best = field_weights[field_name]
                        best_term = original
            if best:
                topic_scores[topic_id] = best
                if best_term:
                    matched_terms.add(best_term)

        if not topic_scores:
            return AcademicMatch(0.0, [], [])

        ordered = sorted(topic_scores.values(), reverse=True)
        score = ordered[0]
        if len(ordered) > 1:
            score += min(0.20, sum(ordered[1:]) * 0.08)
        return AcademicMatch(
            score=min(1.0, round(score, 4)),
            topics=sorted(topic_scores),
            matched_terms=sorted(matched_terms, key=str.casefold),
        )


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def contains_normalized(text: str, phrase: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {text} "
