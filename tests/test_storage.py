from pathlib import Path

from vision_research_monitor.models import NormalizedItem
from vision_research_monitor.storage import JsonlItemStore


def test_jsonl_store_deduplicates_ids_across_reloads(tmp_path: Path) -> None:
    item = NormalizedItem(
        id="github:release:101:release:501",
        source="github",
        source_id="101:release:501",
        kind="release",
        title="example/project v1",
        url="https://github.com/example/project/releases/tag/v1",
        discovered_at="2026-08-08T01:00:00Z",
    )

    assert JsonlItemStore(tmp_path).append([item]) == 1
    assert JsonlItemStore(tmp_path).append([item]) == 0
    lines = next(iter(tmp_path.rglob("*.jsonl"))).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
