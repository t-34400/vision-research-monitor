from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

from vision_research_monitor.http import HttpClient
from vision_research_monitor.sources.cvf import CVFCollector, parse_cvf_detail, parse_cvf_index

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/sources"


def load_inputs() -> tuple[dict, dict]:
    config = yaml.safe_load((ROOT / "config/sources.yaml").read_text())
    config["cvf"]["editions"] = [dict(config["cvf"]["editions"][0])]
    config["cvf"]["editions"][0]["minimum_index_papers"] = 1
    taxonomy = yaml.safe_load((ROOT / "config/taxonomy.yaml").read_text())
    return config, taxonomy


def test_cvf_parsers_preserve_paper_and_external_links() -> None:
    index = parse_cvf_index(
        (FIXTURES / "cvf_index.html").read_text(), "https://openaccess.thecvf.com"
    )
    assert len(index) == 2
    assert index[1].authors == ["Alice Example", "Bob Example"]
    assert index[1].source_id.endswith("Example_Pose-Free_Gaussian_Splatting_CVPR_2026_paper.html")

    detail = parse_cvf_detail(
        (FIXTURES / "cvf_detail.html").read_text(),
        index[1].detail_url,
    )
    assert "sparse unposed images" in detail.abstract
    assert detail.pdf_url == "https://openaccess.thecvf.com/content/CVPR2026/papers/Example.pdf"


def test_cvf_collector_baselines_then_emits_new_relevant_paper_and_project() -> None:
    config, taxonomy = load_inputs()
    index_html = (FIXTURES / "cvf_index.html").read_text()
    detail_html = (FIXTURES / "cvf_detail.html").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("Example_Pose-Free_Gaussian_Splatting_CVPR_2026_paper.html"):
            return httpx.Response(200, text=detail_html)
        return httpx.Response(200, text=index_html)

    old_id = "content/CVPR2026/html/Old_Unrelated_Paper_CVPR_2026_paper.html"
    state = {
        "sources": {
            "cvf": {
                "editions": {
                    "cvpr-2026": {
                        "bootstrapped": True,
                        "paper_ids": [old_id],
                    }
                }
            }
        }
    }
    with HttpClient(
        config["cvf"]["base_url"],
        transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    ) as client:
        result = CVFCollector(
            client,
            state,
            config,
            taxonomy,
            sleeper=lambda _: None,
            monotonic=lambda: 0.0,
        ).collect(datetime(2026, 8, 8, tzinfo=UTC))

    assert result.failed_targets == 0
    paper = next(item for item in result.items if item.kind == "paper")
    project = next(item for item in result.items if item.kind == "project")
    assert "gaussian_splatting" in paper.topics
    assert paper.metadata["code_urls"] == ["https://github.com/example/pose-free-gs"]
    assert paper.metadata["project_urls"] == ["https://example.org/pose-free-gs"]
    assert project.related_items == [paper.id]
    edition_state = state["sources"]["cvf"]["editions"]["cvpr-2026"]
    assert edition_state["bootstrapped"] is True
    assert edition_state["paper_ids"] == [
        "content/CVPR2026/html/Example_Pose-Free_Gaussian_Splatting_CVPR_2026_paper.html",
        old_id,
    ]
    assert edition_state["active_paper_ids"] == edition_state["paper_ids"]


def test_project_sidecar_identity_preserves_parent_relation() -> None:
    from vision_research_monitor.models import NormalizedItem
    from vision_research_monitor.sources.project_pages import project_item_from_url

    first = NormalizedItem(
        id="cvf:paper:first",
        source="cvf",
        source_id="first",
        kind="paper",
        title="First",
        url="https://openaccess.thecvf.com/first",
        discovered_at="2026-08-08T00:00:00Z",
    )
    second = NormalizedItem(
        id="cvf:paper:second",
        source="cvf",
        source_id="second",
        kind="paper",
        title="Second",
        url="https://openaccess.thecvf.com/second",
        discovered_at="2026-08-08T00:00:00Z",
    )

    first_project = project_item_from_url(first, "https://example.org/shared-project")
    second_project = project_item_from_url(second, "https://example.org/shared-project")

    assert first_project.id != second_project.id
    assert first_project.related_items == [first.id]
    assert second_project.related_items == [second.id]


def test_cvf_collector_allows_small_inventory_loss_and_preserves_history() -> None:
    config, taxonomy = load_inputs()
    config["cvf"]["editions"] = [dict(config["cvf"]["editions"][0], minimum_index_papers=1)]
    old_id = "content/CVPR2026/html/Old_Unrelated_Paper_CVPR_2026_paper.html"
    vanished_id = "content/CVPR2026/html/Vanished_Paper_CVPR_2026_paper.html"
    new_id = "content/CVPR2026/html/Example_Pose-Free_Gaussian_Splatting_CVPR_2026_paper.html"
    state = {
        "sources": {
            "cvf": {
                "editions": {
                    "cvpr-2026": {
                        "bootstrapped": True,
                        "paper_ids": [old_id, vanished_id],
                        "active_paper_ids": [old_id, vanished_id],
                    }
                }
            }
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("Example_Pose-Free_Gaussian_Splatting_CVPR_2026_paper.html"):
            return httpx.Response(200, text=(FIXTURES / "cvf_detail.html").read_text())
        if request.url.path == "/CVPR2026":
            return httpx.Response(200, text=(FIXTURES / "cvf_index.html").read_text())
        raise AssertionError(f"unexpected request {request.url}")

    with HttpClient(config["cvf"]["base_url"], transport=httpx.MockTransport(handler)) as client:
        result = CVFCollector(client, state, config, taxonomy, sleeper=lambda _: None).collect(
            datetime(2026, 8, 8, tzinfo=UTC)
        )

    assert result.failed_targets == 0
    assert any(diagnostic["level"] == "warning" for diagnostic in result.diagnostics)
    assert any(item.source_id == new_id for item in result.items)
    edition_state = state["sources"]["cvf"]["editions"]["cvpr-2026"]
    assert edition_state["paper_ids"] == sorted([old_id, vanished_id, new_id])
    assert edition_state["active_paper_ids"] == sorted([old_id, new_id])


def test_cvf_collector_does_not_reemit_reappearing_historical_paper() -> None:
    config, taxonomy = load_inputs()
    old_id = "content/CVPR2026/html/Old_Unrelated_Paper_CVPR_2026_paper.html"
    reappearing_id = (
        "content/CVPR2026/html/Example_Pose-Free_Gaussian_Splatting_CVPR_2026_paper.html"
    )
    state = {
        "sources": {
            "cvf": {
                "editions": {
                    "cvpr-2026": {
                        "bootstrapped": True,
                        "paper_ids": [old_id, reappearing_id],
                        "active_paper_ids": [old_id],
                    }
                }
            }
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/CVPR2026":
            return httpx.Response(200, text=(FIXTURES / "cvf_index.html").read_text())
        raise AssertionError(f"unexpected request {request.url}")

    with HttpClient(config["cvf"]["base_url"], transport=httpx.MockTransport(handler)) as client:
        result = CVFCollector(client, state, config, taxonomy, sleeper=lambda _: None).collect(
            datetime(2026, 8, 8, tzinfo=UTC)
        )

    assert result.failed_targets == 0
    assert result.items == []
    assert result.diagnostics == []
    assert state["sources"]["cvf"]["editions"]["cvpr-2026"]["active_paper_ids"] == sorted(
        [old_id, reappearing_id]
    )


def test_cvf_collector_rejects_inventory_loss_above_guard_without_changing_state() -> None:
    config, taxonomy = load_inputs()
    current_ids = [
        "content/CVPR2026/html/Old_Unrelated_Paper_CVPR_2026_paper.html",
        "content/CVPR2026/html/Example_Pose-Free_Gaussian_Splatting_CVPR_2026_paper.html",
    ]
    vanished_ids = [
        f"content/CVPR2026/html/Vanished_{index}_CVPR_2026_paper.html" for index in range(6)
    ]
    previous_ids = sorted(current_ids + vanished_ids)
    state = {
        "sources": {
            "cvf": {
                "editions": {
                    "cvpr-2026": {
                        "bootstrapped": True,
                        "paper_ids": previous_ids,
                        "active_paper_ids": previous_ids,
                    }
                }
            }
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/CVPR2026":
            return httpx.Response(200, text=(FIXTURES / "cvf_index.html").read_text())
        raise AssertionError(f"unexpected request {request.url}")

    with HttpClient(config["cvf"]["base_url"], transport=httpx.MockTransport(handler)) as client:
        result = CVFCollector(client, state, config, taxonomy, sleeper=lambda _: None).collect(
            datetime(2026, 8, 8, tzinfo=UTC)
        )

    assert result.failed_targets == 1
    assert result.items == []
    diagnostic = result.diagnostics[0]
    assert diagnostic["level"] == "error"
    assert "missing=6" in diagnostic["message"]
    assert "allowed_missing=5" in diagnostic["message"]
    edition_state = state["sources"]["cvf"]["editions"]["cvpr-2026"]
    assert edition_state["paper_ids"] == previous_ids
    assert edition_state["active_paper_ids"] == previous_ids
