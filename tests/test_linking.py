from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from vision_research_monitor.linking.linker import EntityLinker, materialize_related_items
from vision_research_monitor.linking.normalize import canonicalize_url
from vision_research_monitor.models import NormalizedItem

ROOT = Path(__file__).resolve().parents[1]


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config/linking.yaml").read_text(encoding="utf-8"))


def item(
    item_id: str,
    *,
    source: str,
    source_id: str,
    kind: str,
    title: str,
    url: str,
    authors: list[str] | None = None,
    topics: list[str] | None = None,
    metadata: dict | None = None,
    related_items: list[str] | None = None,
) -> NormalizedItem:
    return NormalizedItem(
        id=item_id,
        source=source,
        source_id=source_id,
        kind=kind,
        title=title,
        url=url,
        discovered_at="2026-08-08T00:00:00Z",
        authors=authors or [],
        topics=topics or [],
        metadata=metadata or {},
        related_items=related_items or [],
    )


def edge_between(result, left: str, right: str):
    expected = {left, right}
    return next((edge for edge in result.edges if {edge.left_id, edge.right_id} == expected), None)


def test_canonicalize_url_normalizes_paper_urls_and_tracking_parameters() -> None:
    config = load_config()
    url_config = config["url"]

    assert (
        canonicalize_url(
            "http://arxiv.org/pdf/2608.01234v2.pdf?utm_source=test#page=2",
            tracking_query_prefixes=url_config["tracking_query_prefixes"],
            tracking_query_keys=url_config["tracking_query_keys"],
        )
        == "https://arxiv.org/abs/2608.01234"
    )
    assert (
        canonicalize_url(
            "https://example.org/project/?b=2&utm_medium=x&a=1#demo",
            tracking_query_prefixes=url_config["tracking_query_prefixes"],
            tracking_query_keys=url_config["tracking_query_keys"],
        )
        == "https://example.org/project?a=1&b=2"
    )


def test_exact_external_identifier_links_repository_and_paper() -> None:
    repository = item(
        "github:repository:101",
        source="github",
        source_id="101",
        kind="repository",
        title="research/fast-3d",
        url="https://github.com/research/fast-3d",
        topics=["feed_forward_3d_reconstruction"],
        metadata={"homepage": "https://arxiv.org/abs/2608.01234"},
    )
    paper = item(
        "arxiv:paper:2608.01234",
        source="arxiv",
        source_id="2608.01234",
        kind="paper",
        title="Fast 3D Reconstruction",
        url="https://arxiv.org/abs/2608.01234v2",
        authors=["Alice Example"],
        topics=["feed_forward_3d_reconstruction"],
    )

    result = EntityLinker(load_config()).link(
        [repository, paper], generated_at="2026-08-08T00:00:00Z"
    )

    edge = edge_between(result, repository.id, paper.id)
    assert edge is not None
    assert any(evidence.kind == "exact_identifier" for evidence in edge.evidence)
    assert result.related_items[repository.id] == [paper.id]
    assert list(result.entities.values()) == [[paper.id, repository.id]]


def test_github_repository_events_link_by_stable_repository_id() -> None:
    repository = item(
        "github:repository:101",
        source="github",
        source_id="101",
        kind="repository",
        title="research/fast-3d",
        url="https://github.com/research/fast-3d",
    )
    release = item(
        "github:release:101:release:55",
        source="github",
        source_id="101:release:55",
        kind="release",
        title="research/fast-3d v1.0",
        url="https://github.com/research/fast-3d/releases/tag/v1.0",
    )

    result = EntityLinker(load_config()).link(
        [repository, release], generated_at="2026-08-08T00:00:00Z"
    )

    edge = edge_between(result, repository.id, release.id)
    assert edge is not None
    assert any("github-repository-id:101" in evidence.value for evidence in edge.evidence)


def test_normalized_title_requires_author_support() -> None:
    arxiv = item(
        "arxiv:paper:2608.00001",
        source="arxiv",
        source_id="2608.00001",
        kind="paper",
        title="Metric Depth from Sparse Views: A Simple Baseline",
        url="https://arxiv.org/abs/2608.00001",
        authors=["Alice Smith", "Bob Lee"],
    )
    openreview = item(
        "openreview:paper:abc",
        source="openreview",
        source_id="abc",
        kind="paper",
        title="Metric Depth from Sparse Views - A Simple Baseline",
        url="https://openreview.net/forum?id=abc",
        authors=["Alice Smith", "Bob Lee", "Carol Kim"],
    )

    result = EntityLinker(load_config()).link(
        [arxiv, openreview], generated_at="2026-08-08T00:00:00Z"
    )

    edge = edge_between(result, arxiv.id, openreview.id)
    assert edge is not None
    assert {evidence.kind for evidence in edge.evidence} >= {"normalized_title", "author_overlap"}


def test_fuzzy_title_links_only_with_author_support() -> None:
    arxiv = item(
        "arxiv:paper:2608.01001",
        source="arxiv",
        source_id="2608.01001",
        kind="paper",
        title="Monocular Metric Depth Estimation in the Wild",
        url="https://arxiv.org/abs/2608.01001",
        authors=["Alice Smith", "Bob Lee"],
    )
    openreview = item(
        "openreview:paper:fuzzy",
        source="openreview",
        source_id="fuzzy",
        kind="paper",
        title="Monocular Metric Depth Estimation for the Wild",
        url="https://openreview.net/forum?id=fuzzy",
        authors=["Alice Smith", "Bob Lee"],
    )

    result = EntityLinker(load_config()).link(
        [arxiv, openreview], generated_at="2026-08-08T00:00:00Z"
    )

    edge = edge_between(result, arxiv.id, openreview.id)
    assert edge is not None
    assert {evidence.kind for evidence in edge.evidence} >= {"fuzzy_title", "author_overlap"}


def test_same_title_with_unrelated_authors_is_not_linked() -> None:
    first = item(
        "arxiv:paper:2608.00002",
        source="arxiv",
        source_id="2608.00002",
        kind="paper",
        title="Universal Depth Estimation",
        url="https://arxiv.org/abs/2608.00002",
        authors=["Alice Smith"],
    )
    second = item(
        "openreview:paper:def",
        source="openreview",
        source_id="def",
        kind="paper",
        title="Universal Depth Estimation",
        url="https://openreview.net/forum?id=def",
        authors=["David Jones"],
    )

    result = EntityLinker(load_config()).link([first, second], generated_at="2026-08-08T00:00:00Z")

    assert edge_between(result, first.id, second.id) is None
    assert not result.entities


def test_repository_name_is_only_supporting_evidence_with_topic_overlap() -> None:
    repository = item(
        "github:repository:301",
        source="github",
        source_id="301",
        kind="repository",
        title="research/VGGT",
        url="https://github.com/research/vggt",
        topics=["vision_foundation_models", "multi_view_3d_reconstruction"],
    )
    paper = item(
        "arxiv:paper:2608.00003",
        source="arxiv",
        source_id="2608.00003",
        kind="paper",
        title="VGGT: Visual Geometry Grounded Transformer",
        url="https://arxiv.org/abs/2608.00003",
        authors=["Alice Example"],
        topics=["vision_foundation_models"],
    )
    unrelated = deepcopy(paper)
    unrelated.id = "arxiv:paper:2608.00004"
    unrelated.source_id = "2608.00004"
    unrelated.url = "https://arxiv.org/abs/2608.00004"
    unrelated.topics = ["image_restoration"]

    result = EntityLinker(load_config()).link(
        [repository, paper, unrelated], generated_at="2026-08-08T00:00:00Z"
    )

    edge = edge_between(result, repository.id, paper.id)
    assert edge is not None
    assert {evidence.kind for evidence in edge.evidence} >= {"repository_name", "topic_overlap"}
    assert edge_between(result, repository.id, unrelated.id) is None


def test_generic_repository_name_does_not_create_false_link() -> None:
    repository = item(
        "github:repository:401",
        source="github",
        source_id="401",
        kind="repository",
        title="research/nerf",
        url="https://github.com/research/nerf",
        topics=["nerf"],
    )
    paper = item(
        "arxiv:paper:2608.00005",
        source="arxiv",
        source_id="2608.00005",
        kind="paper",
        title="NeRF for Dynamic Urban Scenes",
        url="https://arxiv.org/abs/2608.00005",
        topics=["nerf"],
    )

    result = EntityLinker(load_config()).link(
        [repository, paper], generated_at="2026-08-08T00:00:00Z"
    )

    assert not result.edges


def test_materialize_related_items_keeps_collected_items_immutable() -> None:
    repository = item(
        "github:repository:501",
        source="github",
        source_id="501",
        kind="repository",
        title="research/model-x",
        url="https://github.com/research/model-x",
    )
    release = item(
        "github:release:501:release:1",
        source="github",
        source_id="501:release:1",
        kind="release",
        title="research/model-x v1",
        url="https://github.com/research/model-x/releases/tag/v1",
    )
    result = EntityLinker(load_config()).link(
        [repository, release], generated_at="2026-08-08T00:00:00Z"
    )

    materialized = materialize_related_items([repository, release], result)

    assert repository.related_items == []
    assert materialized[0].related_items == [release.id]


def test_explicit_project_relation_and_metadata_url_list_are_linked() -> None:
    paper = item(
        "cvf:paper:paper-1",
        source="cvf",
        source_id="paper-1",
        kind="paper",
        title="Pose-Free Gaussian Splatting",
        url="https://openaccess.thecvf.com/content/test.html",
        metadata={"code_urls": ["https://github.com/example/pose-free-gs"]},
    )
    repository = item(
        "github:repository:999",
        source="github",
        source_id="999",
        kind="repository",
        title="example/pose-free-gs",
        url="https://github.com/example/pose-free-gs",
    )
    project = item(
        "cvf:project:abc",
        source="cvf",
        source_id="paper-1:project:abc",
        kind="project",
        title="Project page — Pose-Free Gaussian Splatting",
        url="https://example.org/project",
        related_items=[paper.id],
    )

    result = EntityLinker(load_config()).link(
        [paper, repository, project], generated_at="2026-08-08T00:00:00Z"
    )

    assert edge_between(result, paper.id, repository.id) is not None
    explicit = edge_between(result, paper.id, project.id)
    assert explicit is not None
    assert any(evidence.kind == "explicit_relation" for evidence in explicit.evidence)
