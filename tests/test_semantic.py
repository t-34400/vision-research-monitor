from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from vision_research_monitor.academic.matching import AcademicLexicalMatcher
from vision_research_monitor.classification.evaluation import evaluate
from vision_research_monitor.classification.semantic import (
    LLMClassification,
    SemanticClassificationPipeline,
)
from vision_research_monitor.config import load_academic, load_semantic, load_taxonomy, load_venues

ROOT = Path(__file__).resolve().parents[1]


def load_configs() -> tuple[dict, dict, dict]:
    taxonomy = load_taxonomy(
        ROOT / "config/taxonomy.yaml", ROOT / "config/schemas/taxonomy.schema.json"
    )
    venues = load_venues(ROOT / "config/venues.yaml", ROOT / "config/schemas/venues.schema.json")
    academic = load_academic(
        ROOT / "config/academic.yaml",
        ROOT / "config/schemas/academic.schema.json",
        {venue["id"] for venue in venues["venues"]},
    )
    semantic = load_semantic(
        ROOT / "config/semantic.yaml",
        ROOT / "config/schemas/semantic.schema.json",
        {topic["id"] for topic in taxonomy["topics"]},
    )
    return taxonomy, academic, semantic


def classify(title: str, text: str):
    taxonomy, academic, semantic = load_configs()
    lexical = AcademicLexicalMatcher(taxonomy, academic["matching"]).match(title, text)
    return SemanticClassificationPipeline(taxonomy, semantic).classify(
        title=title,
        text=text,
        lexical_score=lexical.score,
        lexical_topics=lexical.topics,
        matched_terms=lexical.matched_terms,
        lexical_threshold=academic["matching"]["minimum_relevance_score"],
    )


def test_semantic_profile_recovers_sfm_paraphrase() -> None:
    result = classify(
        "Recovering camera motion and sparse geometry from unordered photographs",
        "We jointly estimate cameras and a sparse 3D point structure from an Internet photo collection.",
    )
    assert result.accepted is True
    assert result.topics == ["structure_from_motion"]
    assert result.evidence["method"] == "semantic_profile"
    assert result.evidence["semantic_model"] == "topic-profile-tfidf-v1"


def test_semantic_profile_rejects_non_visual_language_model() -> None:
    result = classify(
        "Large language model theorem proving",
        "We improve formal mathematical reasoning with search and language models.",
    )
    assert result.accepted is False
    assert result.topics == []


def test_semantic_profile_enriches_accepted_lexical_topics() -> None:
    result = classify(
        "Open-Vocabulary Object Detection",
        "Text embeddings enable detection of unseen categories.",
    )
    assert result.accepted is True
    assert result.topics == ["object_detection", "open_vocabulary_recognition"]
    assert result.evidence["method"] == "lexical+semantic_profile"


def test_llm_contract_runs_only_after_low_lexical_candidate_reduction() -> None:
    taxonomy, academic, semantic = load_configs()
    semantic = deepcopy(semantic)
    semantic["llm"].update(
        {
            "enabled": True,
            "minimum_semantic_score": 0.0,
            "maximum_semantic_score": 1.0,
        }
    )

    class FakeLLM:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def classify(
            self, *, title: str, text: str, candidate_topics: list[str]
        ) -> LLMClassification:
            self.calls.append(candidate_topics)
            return LLMClassification(
                True, candidate_topics[:1], 0.88, "fixture decision", "fixture-llm-v1"
            )

    fake = FakeLLM()
    pipeline = SemanticClassificationPipeline(taxonomy, semantic, llm_classifier=fake)
    lexical_matcher = AcademicLexicalMatcher(taxonomy, academic["matching"])
    threshold = academic["matching"]["minimum_relevance_score"]

    accepted = lexical_matcher.match("Fast NeRF Rendering", "Neural radiance field rendering")
    pipeline.classify(
        title="Fast NeRF Rendering",
        text="Neural radiance field rendering",
        lexical_score=accepted.score,
        lexical_topics=accepted.topics,
        matched_terms=accepted.matched_terms,
        lexical_threshold=threshold,
    )
    assert fake.calls == []

    low = lexical_matcher.match(
        "Recovering camera motion and sparse geometry from unordered photographs",
        "We jointly estimate cameras and a sparse 3D point structure.",
    )
    result = pipeline.classify(
        title="Recovering camera motion and sparse geometry from unordered photographs",
        text="We jointly estimate cameras and a sparse 3D point structure.",
        lexical_score=low.score,
        lexical_topics=low.topics,
        matched_terms=low.matched_terms,
        lexical_threshold=threshold,
    )
    assert fake.calls == [["structure_from_motion"]]
    assert result.evidence["method"] == "llm"
    assert result.evidence["llm_model"] == "fixture-llm-v1"


def test_reviewed_evaluation_improves_over_lexical_baseline() -> None:
    taxonomy, academic, semantic = load_configs()
    payload = yaml.safe_load((ROOT / "evaluation/semantic_cases.yaml").read_text(encoding="utf-8"))
    result = evaluate(payload["cases"], taxonomy, academic, semantic)
    assert result.semantic.f1 > result.lexical.f1
    assert result.semantic.precision >= 0.9
    assert result.semantic.recall >= 0.9


def test_llm_failure_falls_back_to_semantic_result() -> None:
    taxonomy, academic, semantic = load_configs()
    semantic = deepcopy(semantic)
    semantic["llm"].update(
        {
            "enabled": True,
            "minimum_semantic_score": 0.0,
            "maximum_semantic_score": 1.0,
        }
    )

    class BrokenLLM:
        def classify(
            self, *, title: str, text: str, candidate_topics: list[str]
        ) -> LLMClassification:
            raise RuntimeError("provider unavailable")

    pipeline = SemanticClassificationPipeline(taxonomy, semantic, llm_classifier=BrokenLLM())
    lexical_matcher = AcademicLexicalMatcher(taxonomy, academic["matching"])
    match = lexical_matcher.match(
        "Recovering camera motion and sparse geometry from unordered photographs",
        "We jointly estimate cameras and a sparse 3D point structure.",
    )
    result = pipeline.classify(
        title="Recovering camera motion and sparse geometry from unordered photographs",
        text="We jointly estimate cameras and a sparse 3D point structure.",
        lexical_score=match.score,
        lexical_topics=match.topics,
        matched_terms=match.matched_terms,
        lexical_threshold=academic["matching"]["minimum_relevance_score"],
    )
    assert result.accepted is True
    assert result.topics == ["structure_from_motion"]
    assert result.evidence["method"] == "semantic_profile"
    assert result.evidence["llm_error"] == "RuntimeError"


def test_semantic_enrichment_requires_each_added_topic_to_clear_threshold() -> None:
    taxonomy, _, semantic = load_configs()
    pipeline = SemanticClassificationPipeline(taxonomy, semantic)

    result = pipeline.classify(
        title="saurav80325-create/leafsense-ai",
        text=(
            "AI-powered plant disease detection system built with TensorFlow, Flask, MobileNetV2, "
            "and CNN for real-time leaf image classification."
        ),
        lexical_score=0.43,
        lexical_topics=["image_classification"],
        matched_terms=["image classification"],
        lexical_threshold=0.40,
    )

    assert result.topics == ["image_classification"]
    assert result.evidence["semantic_topic_scores"] == {"image_classification": 0.263181}
