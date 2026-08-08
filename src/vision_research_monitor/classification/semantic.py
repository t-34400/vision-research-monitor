from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True, frozen=True)
class LLMClassification:
    relevant: bool
    topics: list[str]
    relevance: float
    reason: str
    model_id: str


class LLMTopicClassifier(Protocol):
    def classify(
        self,
        *,
        title: str,
        text: str,
        candidate_topics: list[str],
    ) -> LLMClassification: ...


@dataclass(slots=True, frozen=True)
class ClassificationResult:
    accepted: bool
    relevance: float
    topics: list[str]
    matched_terms: list[str]
    evidence: dict[str, Any]


@dataclass(slots=True, frozen=True)
class SemanticMatch:
    best_score: float
    topics: list[str]
    topic_scores: dict[str, float]


class TopicProfileTfidf:
    def __init__(self, taxonomy: dict[str, Any], config: dict[str, Any]) -> None:
        self.model = config["model"]
        self.classification = config["classification"]
        hints_by_topic = {profile["topic"]: profile["hints"] for profile in config["profiles"]}
        self._required_any = {
            profile["topic"]: list(profile.get("required_any", []))
            for profile in config["profiles"]
        }
        self._required_groups = {
            profile["topic"]: [list(group) for group in profile.get("required_groups", [])]
            for profile in config["profiles"]
        }
        self._topic_documents: dict[str, str] = {}
        for topic in taxonomy["topics"]:
            fragments = [topic["label"], *topic["aliases"], *hints_by_topic[topic["id"]]]
            self._topic_documents[topic["id"]] = " ".join(fragments)

        feature_sets = {
            topic_id: set(self._raw_features(text))
            for topic_id, text in self._topic_documents.items()
        }
        document_count = len(feature_sets)
        document_frequency: Counter[str] = Counter()
        for features in feature_sets.values():
            document_frequency.update(features)
        self._idf = {
            feature: math.log((1 + document_count) / (1 + frequency)) + 1.0
            for feature, frequency in document_frequency.items()
        }
        self._topic_vectors = {
            topic_id: self._vectorize(text) for topic_id, text in self._topic_documents.items()
        }

    @property
    def model_id(self) -> str:
        return str(self.model["id"])

    def match(self, title: str, text: str) -> SemanticMatch:
        candidate = self._vectorize(f"{title} {title} {text}")
        if not candidate:
            return SemanticMatch(0.0, [], {})

        normalized_candidate = normalize_text(f"{title} {text}")
        candidate_tokens = normalized_candidate.split()
        scores = {}
        for topic_id, topic_vector in self._topic_vectors.items():
            required = self._required_any.get(topic_id, [])
            if required and not any(
                anchor_matches(normalized_candidate, candidate_tokens, anchor)
                for anchor in required
            ):
                scores[topic_id] = 0.0
                continue
            groups = self._required_groups.get(topic_id, [])
            if groups and not all(
                any(
                    anchor_matches(normalized_candidate, candidate_tokens, anchor)
                    for anchor in group
                )
                for group in groups
            ):
                scores[topic_id] = 0.0
                continue
            scores[topic_id] = round(dot(candidate, topic_vector), 6)
        ordered = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
        if not ordered:
            return SemanticMatch(0.0, [], {})
        best_score = ordered[0][1]
        minimum = float(self.classification["minimum_topic_similarity"])
        relative = float(self.classification["relative_topic_ratio"])
        limit = int(self.classification["maximum_topics"])
        selected = [
            topic_id
            for topic_id, score in ordered
            if score >= minimum and score >= best_score * relative
        ][:limit]
        return SemanticMatch(
            best_score=best_score,
            topics=selected,
            topic_scores={topic_id: scores[topic_id] for topic_id in selected},
        )

    def relevance(self, similarity: float) -> float:
        full_scale = float(self.classification["full_scale_similarity"])
        if full_scale <= 0:
            return 0.0
        return round(max(0.0, min(1.0, similarity / full_scale)), 4)

    def _vectorize(self, text: str) -> dict[str, float]:
        counts = Counter(self._raw_features(text))
        weighted: dict[str, float] = {}
        for feature, count in counts.items():
            idf = self._idf.get(feature)
            if idf is None:
                continue
            type_weight = float(
                self.model["char_weight"] if feature.startswith("c:") else self.model["word_weight"]
            )
            weighted[feature] = (1.0 + math.log(count)) * idf * type_weight
        norm = math.sqrt(sum(value * value for value in weighted.values()))
        if norm == 0:
            return {}
        return {feature: value / norm for feature, value in weighted.items()}

    def _raw_features(self, text: str) -> list[str]:
        normalized = normalize_text(text)
        words = normalized.split()
        features: list[str] = []
        word_min = int(self.model["word_ngram_min"])
        word_max = int(self.model["word_ngram_max"])
        for size in range(word_min, word_max + 1):
            for index in range(0, len(words) - size + 1):
                features.append("w:" + " ".join(words[index : index + size]))

        char_min = int(self.model["char_ngram_min"])
        char_max = int(self.model["char_ngram_max"])
        for word in words:
            padded = f" {word} "
            for size in range(char_min, char_max + 1):
                for index in range(0, len(padded) - size + 1):
                    features.append("c:" + padded[index : index + size])
        return features


class SemanticClassificationPipeline:
    def __init__(
        self,
        taxonomy: dict[str, Any],
        config: dict[str, Any],
        *,
        llm_classifier: LLMTopicClassifier | None = None,
    ) -> None:
        self.config = config
        self.semantic = TopicProfileTfidf(taxonomy, config)
        self.llm_classifier = llm_classifier

    def classify(
        self,
        *,
        title: str,
        text: str,
        lexical_score: float,
        lexical_topics: list[str],
        matched_terms: list[str],
        lexical_threshold: float,
    ) -> ClassificationResult:
        evidence: dict[str, Any]
        if lexical_score >= lexical_threshold:
            topics = set(lexical_topics)
            evidence = {
                "method": "lexical",
                "lexical_score": round(float(lexical_score), 4),
                "semantic_model": None,
                "llm_model": None,
            }
            if self.config.get("enabled", True):
                semantic = self.semantic.match(title, text)
                if semantic.best_score >= float(
                    self.config["classification"]["enrichment_similarity"]
                ):
                    topics.update(semantic.topics)
                    evidence.update(
                        {
                            "method": "lexical+semantic_profile",
                            "semantic_model": self.semantic.model_id,
                            "semantic_similarity": round(semantic.best_score, 6),
                            "semantic_topic_scores": semantic.topic_scores,
                        }
                    )
            return ClassificationResult(
                accepted=True,
                relevance=round(float(lexical_score), 4),
                topics=sorted(topics),
                matched_terms=sorted(set(matched_terms), key=str.casefold),
                evidence=evidence,
            )

        if not self.config.get("enabled", True):
            return rejected_lexical(lexical_score, lexical_topics, matched_terms)

        semantic = self.semantic.match(title, text)
        semantic_relevance = self.semantic.relevance(semantic.best_score)
        acceptance_similarity = float(self.config["classification"]["acceptance_similarity"])
        evidence = {
            "method": "semantic_profile",
            "lexical_score": round(float(lexical_score), 4),
            "semantic_model": self.semantic.model_id,
            "semantic_similarity": round(semantic.best_score, 6),
            "semantic_topic_scores": semantic.topic_scores,
            "llm_model": None,
        }

        try:
            llm = self._maybe_classify_with_llm(title, text, semantic)
        except Exception as exc:
            evidence["llm_error"] = type(exc).__name__
            llm = None
        if llm is not None:
            maximum = int(self.config["llm"]["maximum_candidate_topics"])
            allowed_topics = set(semantic.topics[:maximum])
            selected_topics = sorted(set(llm.topics) & allowed_topics)
            accepted = llm.relevant and bool(selected_topics)
            evidence.update(
                {
                    "method": "llm",
                    "llm_model": llm.model_id,
                    "llm_reason": llm.reason,
                }
            )
            return ClassificationResult(
                accepted=accepted,
                relevance=round(max(0.0, min(1.0, llm.relevance)), 4)
                if accepted
                else round(float(lexical_score), 4),
                topics=selected_topics if accepted else [],
                matched_terms=sorted(set(matched_terms), key=str.casefold),
                evidence=evidence,
            )

        accepted = semantic.best_score >= acceptance_similarity and bool(semantic.topics)
        return ClassificationResult(
            accepted=accepted,
            relevance=semantic_relevance if accepted else round(float(lexical_score), 4),
            topics=semantic.topics if accepted else [],
            matched_terms=sorted(set(matched_terms), key=str.casefold),
            evidence=evidence,
        )

    def _maybe_classify_with_llm(
        self,
        title: str,
        text: str,
        semantic: SemanticMatch,
    ) -> LLMClassification | None:
        llm_config = self.config["llm"]
        if (
            not llm_config.get("enabled", False)
            or self.llm_classifier is None
            or not semantic.topics
        ):
            return None
        if not (
            float(llm_config["minimum_semantic_score"])
            <= semantic.best_score
            <= float(llm_config["maximum_semantic_score"])
        ):
            return None
        candidate_topics = semantic.topics[: int(llm_config["maximum_candidate_topics"])]
        return self.llm_classifier.classify(
            title=title, text=text, candidate_topics=candidate_topics
        )


def rejected_lexical(
    lexical_score: float,
    lexical_topics: list[str],
    matched_terms: list[str],
) -> ClassificationResult:
    return ClassificationResult(
        accepted=False,
        relevance=round(float(lexical_score), 4),
        topics=sorted(set(lexical_topics)),
        matched_terms=sorted(set(matched_terms), key=str.casefold),
        evidence={
            "method": "lexical",
            "lexical_score": round(float(lexical_score), 4),
            "semantic_model": None,
            "llm_model": None,
        },
    )


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def anchor_matches(normalized_text: str, tokens: list[str], anchor: str) -> bool:
    normalized_anchor = normalize_text(anchor.rstrip("*"))
    if not normalized_anchor:
        return False
    if anchor.endswith("*"):
        return any(token.startswith(normalized_anchor) for token in tokens)
    if " " in normalized_anchor:
        return f" {normalized_anchor} " in f" {normalized_text} "
    return normalized_anchor in tokens


def dot(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(feature, 0.0) for feature, value in left.items())
