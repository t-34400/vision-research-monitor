from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ..academic.matching import AcademicLexicalMatcher
from .semantic import SemanticClassificationPipeline


@dataclass(slots=True, frozen=True)
class Metrics:
    precision: float
    recall: float
    f1: float
    exact_match: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class EvaluationResult:
    cases: int
    lexical: Metrics
    semantic: Metrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "cases": self.cases,
            "lexical": self.lexical.to_dict(),
            "semantic": self.semantic.to_dict(),
            "delta_f1": round(self.semantic.f1 - self.lexical.f1, 4),
        }


def evaluate(
    cases: list[dict[str, Any]],
    taxonomy: dict[str, Any],
    academic_config: dict[str, Any],
    semantic_config: dict[str, Any],
) -> EvaluationResult:
    lexical_matcher = AcademicLexicalMatcher(taxonomy, academic_config["matching"])
    semantic_pipeline = SemanticClassificationPipeline(taxonomy, semantic_config)
    threshold = float(academic_config["matching"]["minimum_relevance_score"])

    expected: list[set[str]] = []
    lexical_predictions: list[set[str]] = []
    semantic_predictions: list[set[str]] = []

    for case in cases:
        expected_topics = set(case["expected_topics"])
        match = lexical_matcher.match(case["title"], case["text"])
        lexical_topics = set(match.topics) if match.score >= threshold else set()
        classification = semantic_pipeline.classify(
            title=case["title"],
            text=case["text"],
            lexical_score=match.score,
            lexical_topics=match.topics,
            matched_terms=match.matched_terms,
            lexical_threshold=threshold,
        )
        semantic_topics = set(classification.topics) if classification.accepted else set()

        expected.append(expected_topics)
        lexical_predictions.append(lexical_topics)
        semantic_predictions.append(semantic_topics)

    return EvaluationResult(
        cases=len(cases),
        lexical=metrics(expected, lexical_predictions),
        semantic=metrics(expected, semantic_predictions),
    )


def metrics(expected: list[set[str]], predicted: list[set[str]]) -> Metrics:
    true_positive = false_positive = false_negative = exact = 0
    for expected_topics, predicted_topics in zip(expected, predicted, strict=True):
        true_positive += len(expected_topics & predicted_topics)
        false_positive += len(predicted_topics - expected_topics)
        false_negative += len(expected_topics - predicted_topics)
        exact += int(expected_topics == predicted_topics)

    precision = safe_divide(true_positive, true_positive + false_positive)
    recall = safe_divide(true_positive, true_positive + false_negative)
    f1 = safe_divide(2 * precision * recall, precision + recall)
    return Metrics(
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        exact_match=round(safe_divide(exact, len(expected)), 4),
    )


def safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
