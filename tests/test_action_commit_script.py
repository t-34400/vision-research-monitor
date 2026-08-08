from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github/scripts/commit-runtime-changes.sh"


def git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )


def test_commit_helper_skips_absent_items_path_and_commits_state(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    remote.mkdir()
    git("init", "--bare", "--initial-branch=main", cwd=remote)

    repo.mkdir()
    git("init", "--initial-branch=main", cwd=repo)
    git("remote", "add", "origin", str(remote), cwd=repo)
    (repo / "data/state").mkdir(parents=True)
    state = repo / "data/state/github_watch.json"
    state.write_text('{"baseline": true}\n')
    git("add", "data/state/github_watch.json", cwd=repo)
    git(
        "-c",
        "user.name=test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-m",
        "seed",
        cwd=repo,
    )
    git("push", "-u", "origin", "main", cwd=repo)

    state.write_text('{"baseline": false}\n')
    env = os.environ | {"CANONICAL_BRANCH": "main"}
    result = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "Update GitHub watch data",
            "data/items",
            "data/state/github_watch.json",
        ],
        cwd=repo,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )

    assert "pathspec" not in result.stderr.lower()
    assert git("log", "-1", "--pretty=%s", cwd=repo).stdout.strip() == "Update GitHub watch data"
    assert not (repo / "data/items").exists()
    assert git("status", "--porcelain", cwd=repo).stdout == ""
