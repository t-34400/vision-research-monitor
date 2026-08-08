from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
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


def workflow_text(name: str) -> str:
    return (WORKFLOWS / name).read_text()


def test_only_active_workflows_are_scheduled() -> None:
    assert {path.name for path in WORKFLOWS.glob("*.yml")} == ACTIVE_WORKFLOWS
    assert not (WORKFLOWS / "collect-openreview.yml").exists()


def test_workflows_use_locked_uv_runtime_and_default_branch() -> None:
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
        assert "contents: write" in text


def test_workflow_commits_are_allowlisted_and_protect_manifest() -> None:
    for name in ACTIVE_WORKFLOWS:
        text = workflow_text(name)
        assert "git add ." not in text
        assert "git add -A" not in text
        assert "git add --" in text
        assert 'git pull --rebase origin "$CANONICAL_BRANCH"' in text
        assert 'git push origin "HEAD:$CANONICAL_BRANCH"' in text
        assert "git diff --quiet -- .chatgpt-workspace-manifest.json" in text
        add_lines = [
            line.strip() for line in text.splitlines() if line.strip().startswith("git add --")
        ]
        assert add_lines
        assert all(".chatgpt-workspace-manifest.json" not in line for line in add_lines)


def test_collectors_stage_only_their_state_file() -> None:
    expected = {
        "collect-arxiv.yml": "data/state/arxiv.json",
        "collect-cvf.yml": "data/state/cvf.json",
        "collect-github-discovery.yml": "data/state/github_discovery.json",
        "collect-github-watch.yml": "data/state/github_watch.json",
        "collect-huggingface.yml": "data/state/huggingface.json",
        "collect-research-blogs.yml": "data/state/research_blogs.json",
    }
    for name, state_path in expected.items():
        add_line = next(
            line.strip()
            for line in workflow_text(name).splitlines()
            if line.strip().startswith("git add --")
        )
        assert add_line == f"git add -- data/items {state_path}"
