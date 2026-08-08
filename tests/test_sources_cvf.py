from datetime import datetime, timezone
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
    index = parse_cvf_index((FIXTURES / "cvf_index.html").read_text(), "https://openaccess.thecvf.com")
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
        ).collect(datetime(2026, 8, 8, tzinfo=timezone.utc))

    assert result.failed_targets == 0
    paper = next(item for item in result.items if item.kind == "paper")
    project = next(item for item in result.items if item.kind == "project")
    assert "gaussian_splatting" in paper.topics
    assert paper.metadata["code_urls"] == ["https://github.com/example/pose-free-gs"]
    assert paper.metadata["project_urls"] == ["https://example.org/pose-free-gs"]
    assert project.related_items == [paper.id]
    assert state["sources"]["cvf"]["editions"]["cvpr-2026"]["bootstrapped"] is True


def test_project_sidecar_identity_preserves_parent_relation() -> None:
    from vision_research_monitor.models import NormalizedItem
    from vision_research_monitor.sources.project_pages import project_item_from_url

    first = NormalizedItem(
        id="cvf:paper:first", source="cvf", source_id="first", kind="paper",
        title="First", url="https://openaccess.thecvf.com/first",
        discovered_at="2026-08-08T00:00:00Z",
    )
    second = NormalizedItem(
        id="cvf:paper:second", source="cvf", source_id="second", kind="paper",
        title="Second", url="https://openaccess.thecvf.com/second",
        discovered_at="2026-08-08T00:00:00Z",
    )

    first_project = project_item_from_url(first, "https://example.org/shared-project")
    second_project = project_item_from_url(second, "https://example.org/shared-project")

    assert first_project.id != second_project.id
    assert first_project.related_items == [first.id]
    assert second_project.related_items == [second.id]


def test_cvf_collector_rejects_inventory_that_loses_known_papers() -> None:
    config, taxonomy = load_inputs()
    config["cvf"]["editions"] = [dict(config["cvf"]["editions"][0], minimum_index_papers=1)]
    state = {
        "sources": {
            "cvf": {
                "editions": {
                    "cvpr-2026": {
                        "bootstrapped": True,
                        "paper_ids": [
                            "content/CVPR2026/html/Old_Unrelated_Paper_CVPR_2026_paper.html",
                            "content/CVPR2026/html/Vanished_Paper_CVPR_2026_paper.html",
                        ],
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
            datetime(2026, 8, 8, tzinfo=timezone.utc)
        )

    assert result.failed_targets == 1
    assert result.items == []
    assert state["sources"]["cvf"]["editions"]["cvpr-2026"]["paper_ids"] == [
        "content/CVPR2026/html/Old_Unrelated_Paper_CVPR_2026_paper.html",
        "content/CVPR2026/html/Vanished_Paper_CVPR_2026_paper.html",
    ]
