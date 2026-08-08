from pathlib import Path

from vision_research_monitor.cli import build_digest, build_trends, link_items, search_archive
from vision_research_monitor.models import NormalizedItem
from vision_research_monitor.runtime import PROJECT_ROOT, RuntimePaths
from vision_research_monitor.storage import JsonlItemStore


def test_runtime_paths_default_to_project_tree(monkeypatch) -> None:
    monkeypatch.delenv("VRM_WORK_ROOT", raising=False)

    paths = RuntimePaths.resolve()

    assert paths.root == PROJECT_ROOT
    assert paths.items == PROJECT_ROOT / "data/items"
    assert paths.daily_reports == PROJECT_ROOT / "reports/daily"


def test_runtime_paths_resolve_relative_environment_root_from_project(monkeypatch) -> None:
    monkeypatch.setenv("VRM_WORK_ROOT", ".local/smoke")

    paths = RuntimePaths.resolve()

    assert paths.root == (PROJECT_ROOT / ".local/smoke").resolve()
    assert paths.items == (PROJECT_ROOT / ".local/smoke/data/items").resolve()
    assert paths.trend_reports == (PROJECT_ROOT / ".local/smoke/reports/trends").resolve()


def test_explicit_work_root_overrides_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VRM_WORK_ROOT", ".local/from-env")

    paths = RuntimePaths.resolve(tmp_path)

    assert paths.root == tmp_path.resolve()


def test_pipeline_derived_outputs_stay_inside_work_root(tmp_path: Path, capsys) -> None:
    paths = RuntimePaths.resolve(tmp_path)
    item = NormalizedItem(
        id="github:repository:runtime-test",
        source="github",
        source_id="runtime-test",
        kind="repository",
        title="Runtime Test Repository",
        url="https://github.com/example/runtime-test",
        discovered_at="2026-08-08T09:00:00Z",
        topics=["object_detection"],
    )
    JsonlItemStore(paths.items).append([item])

    assert link_items.main(["--work-root", str(tmp_path)]) == 0
    assert build_digest.main(["--work-root", str(tmp_path), "--date", "2026-08-09"]) == 0
    assert build_trends.main(["--work-root", str(tmp_path), "--date", "2026-08-09"]) == 0
    assert search_archive.main(["--work-root", str(tmp_path), "Runtime Test"]) == 0
    capsys.readouterr()

    assert (paths.entities / "links.json").is_file()
    assert (paths.ranking / "2026-08-09.json").is_file()
    assert (paths.analytics / "2026-08-09.json").is_file()
    assert (paths.archive / "index.json").is_file()
    assert (paths.daily_reports / "2026-08-09.md").is_file()
    assert (paths.trend_reports / "2026-08-09.md").is_file()
