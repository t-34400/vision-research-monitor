from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
COMMIT_SCRIPT = ROOT / ".github/scripts/commit-runtime-changes.sh"
ACTIVE_WORKFLOWS = {
    "build-digest.yml",
    "collect-arxiv.yml",
    "collect-cvf.yml",
    "collect-github-discovery.yml",
    "collect-github-watch.yml",
    "collect-huggingface.yml",
    "collect-research-blogs.yml",
}
SETUP_UV_REVISION = "c771a70e6277c0a99b617c7a806ffedaca235ff9"
EXPECTED_DAILY_CRONS = {
    "collect-github-watch.yml": "5 8 * * *",
    "collect-arxiv.yml": "10 8 * * *",
    "collect-huggingface.yml": "15 8 * * *",
    "collect-cvf.yml": "20 8 * * *",
    "collect-research-blogs.yml": "25 8 * * *",
    "collect-github-discovery.yml": "30 8 * * *",
    "build-digest.yml": "45 8 * * *",
}


def workflow_text(name: str) -> str:
    return (WORKFLOWS / name).read_text()


def test_only_active_workflows_are_scheduled() -> None:
    assert {path.name for path in WORKFLOWS.glob("*.yml")} == ACTIVE_WORKFLOWS
    assert not (WORKFLOWS / "collect-openreview.yml").exists()


def test_workflows_use_daily_morning_schedule() -> None:
    for name, cron in EXPECTED_DAILY_CRONS.items():
        text = workflow_text(name)
        assert text.count("- cron:") == 1
        assert f'- cron: "{cron}"' in text
        assert 'timezone: "Asia/Tokyo"' in text


def test_workflows_use_locked_uv_runtime_and_queued_default_branch_writes() -> None:
    for name in ACTIVE_WORKFLOWS:
        text = workflow_text(name)
        assert "actions/setup-python" not in text
        assert "pip install" not in text
        assert f"astral-sh/setup-uv@{SETUP_UV_REVISION}" in text
        assert 'version: "0.12.3"' in text
        assert 'python-version: "3.13"' in text
        assert "uv sync --locked --no-dev" in text
        assert "uv run --locked --no-sync" in text
        assert "ref: ${{ github.event.repository.default_branch }}" in text
        assert "CANONICAL_BRANCH: ${{ github.event.repository.default_branch }}" in text
        assert "group: research-monitor-writes" in text
        assert "queue: max" in text
        assert "cancel-in-progress: false" in text
        assert "contents: write" in text


def test_workflow_commits_use_shared_allowlisted_helper_and_protect_manifest() -> None:
    helper = COMMIT_SCRIPT.read_text()
    assert 'git add -- "$path"' in helper
    assert "git add ." not in helper
    assert "git add -A" not in helper
    assert 'git pull --rebase origin "$CANONICAL_BRANCH"' in helper
    assert 'git push origin "HEAD:$CANONICAL_BRANCH"' in helper

    for name in ACTIVE_WORKFLOWS:
        text = workflow_text(name)
        assert ".github/scripts/commit-runtime-changes.sh" in text
        assert "git add ." not in text
        assert "git add -A" not in text
        assert "git diff --quiet -- .chatgpt-workspace-manifest.json" in text
        commit_lines = [
            line.strip()
            for line in text.splitlines()
            if ".github/scripts/commit-runtime-changes.sh" in line
        ]
        assert commit_lines
        assert all(".chatgpt-workspace-manifest.json" not in line for line in commit_lines)


def test_collectors_pass_only_their_state_file_and_items_to_commit_helper() -> None:
    expected = {
        "collect-arxiv.yml": "data/state/arxiv.json",
        "collect-cvf.yml": "data/state/cvf.json",
        "collect-github-discovery.yml": "data/state/github_discovery.json",
        "collect-github-watch.yml": "data/state/github_watch.json",
        "collect-huggingface.yml": "data/state/huggingface.json",
        "collect-research-blogs.yml": "data/state/research_blogs.json",
    }
    for name, state_path in expected.items():
        commit_line = next(
            line.strip()
            for line in workflow_text(name).splitlines()
            if ".github/scripts/commit-runtime-changes.sh" in line
        )
        if name == "collect-github-discovery.yml":
            assert commit_line.endswith(
                f"data/items {state_path} data/state/github_auto_watch.json"
            )
        else:
            assert commit_line.endswith(f"data/items {state_path}")
