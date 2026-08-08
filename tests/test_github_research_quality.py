from pathlib import Path

import yaml

from vision_research_monitor.github.research_quality import assess_repository_research_quality

ROOT = Path(__file__).resolve().parents[1]


def load_quality_config() -> dict:
    config = yaml.safe_load((ROOT / "config/github_discovery.yaml").read_text(encoding="utf-8"))
    return config["research_quality"]


def test_research_quality_keeps_research_framework_and_suppresses_generic_app() -> None:
    config = load_quality_config()
    framework = {
        "full_name": "torch-uncertainty/torch-uncertainty",
        "description": "Open-source framework for uncertainty and deep learning models in PyTorch",
        "topics": ["computer-vision"],
        "stargazers_count": 524,
        "homepage": "https://torch-uncertainty.github.io",
    }
    generic_app = {
        "full_name": "example/real-time-object-detection",
        "description": "Real-time object detection application using YOLO and OpenCV",
        "topics": ["computer-vision"],
        "stargazers_count": 5000,
        "homepage": "",
    }

    research = assess_repository_research_quality(
        framework,
        venue_hits={("cvpr", 2025, "CVPR")},
        config=config,
    )
    application = assess_repository_research_quality(
        generic_app,
        venue_hits=set(),
        config=config,
    )

    assert research.category == "research"
    assert research.score >= config["research_candidate_score"]
    assert application.score < config["research_candidate_score"]


def test_research_quality_caps_awesome_lists_and_tutorials() -> None:
    config = load_quality_config()
    collection = {
        "full_name": "ai4s-research/awesome-ai-for-science",
        "description": "A curated list of AI papers, datasets, libraries, and frameworks",
        "topics": ["awesome-list"],
        "stargazers_count": 1841,
        "homepage": "https://example.org",
    }
    tutorial = {
        "full_name": "example/openrouter-intro-tutorial",
        "description": "Hands-on introduction with a small object detection example",
        "topics": [],
        "stargazers_count": 0,
        "homepage": "",
    }

    collection_result = assess_repository_research_quality(
        collection,
        venue_hits={("cvpr", 2026, "CVPR")},
        config=config,
    )
    tutorial_result = assess_repository_research_quality(
        tutorial,
        venue_hits=set(),
        config=config,
    )

    assert collection_result.category == "collection"
    assert collection_result.score == config["collection_cap"]
    assert tutorial_result.category == "tutorial"
    assert tutorial_result.score <= config["tutorial_cap"]
