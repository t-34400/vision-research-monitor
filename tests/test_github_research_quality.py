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
        readme="A Python library and framework for running the application.",
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


def test_readme_lead_can_identify_collection_repository() -> None:
    config = load_quality_config()
    repository = {
        "full_name": "example/LLMEvaluation",
        "description": "A comprehensive guide to language-model evaluation methods",
        "topics": ["llm-evaluation"],
        "stargazers_count": 1000,
        "homepage": "https://example.org",
    }

    result = assess_repository_research_quality(
        repository,
        venue_hits={("cvpr", 2026, "CVPR")},
        config=config,
        readme="# Awesome LLM Evaluation\nA compendium and curated list of evaluation papers.",
    )

    assert result.category == "collection"
    assert result.score == config["collection_cap"]


def test_readme_supporting_terms_do_not_make_generic_project_research() -> None:
    config = load_quality_config()
    repository = {
        "full_name": "student/fashion-image-classification-deep-learning",
        "description": "Fashion image classification deep-learning project",
        "topics": ["computer-vision"],
        "stargazers_count": 0,
        "homepage": "",
    }

    result = assess_repository_research_quality(
        repository,
        venue_hits=set(),
        config=config,
        readme="Dataset preparation, training code, evaluation code, and pretrained model.",
    )

    assert result.category == "candidate"
    assert result.score < config["research_candidate_score"]
    assert "supporting_research_term" in result.signals


def test_readme_publication_links_only_count_near_the_readme_lead() -> None:
    config = load_quality_config()
    repository = {
        "full_name": "example/general-library",
        "description": "General software library for data processing",
        "topics": [],
        "stargazers_count": 0,
        "homepage": "",
    }
    readme = (
        "General library documentation. "
        + "x" * (config["readme_evidence_characters"] + 100)
        + " References https://arxiv.org/abs/2601.99999"
    )

    result = assess_repository_research_quality(
        repository, venue_hits=set(), config=config, readme=readme
    )

    assert result.score < config["research_candidate_score"]
    assert "publication_link" not in result.signals


def test_readme_lead_with_paper_evidence_is_research() -> None:
    config = load_quality_config()
    repository = {
        "full_name": "research/new-geometry-model",
        "description": "Geometry model for images",
        "topics": ["computer-vision"],
        "stargazers_count": 0,
        "homepage": "",
    }

    result = assess_repository_research_quality(
        repository,
        venue_hits=set(),
        config=config,
        readme="Official implementation of our paper https://arxiv.org/abs/2601.12345",
    )

    assert result.category == "research"
    assert result.score >= config["research_candidate_score"]
    assert "research_term" in result.signals
    assert "publication_link" in result.signals


def test_identity_level_kaggle_portfolio_and_interview_repositories_are_capped() -> None:
    config = load_quality_config()
    cases = [
        ("student/Kaggle-EV-Purchase-Prediction", "Kaggle competition project"),
        ("student/automation-portfolio", "Automation portfolio with image examples"),
        ("student/ai-engineering-interview-questions", "AI engineering interview questions"),
    ]

    for full_name, description in cases:
        result = assess_repository_research_quality(
            {
                "full_name": full_name,
                "description": description,
                "topics": ["computer-vision"],
                "stargazers_count": 5000,
                "homepage": "https://example.org",
            },
            venue_hits=set(),
            config=config,
            readme="Official implementation https://arxiv.org/abs/2601.12345",
        )
        assert result.category == "tutorial"
        assert result.score <= config["tutorial_cap"]
