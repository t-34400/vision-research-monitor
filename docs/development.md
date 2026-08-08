# Development Environment

The project uses [uv](https://docs.astral.sh/uv/) for Python installation,
dependency locking, environment synchronization, and command execution.

## Requirements

Install a recent uv release. Python itself does not need to be installed
separately when uv is allowed to manage Python installations.

The repository pins Python 3.13 through `.python-version`. The supported project
range is declared in `pyproject.toml` as `>=3.13,<3.14` so local development and
GitHub Actions use the same Python minor version.

## First setup

From the repository root, bootstrap the lockfile once:

```bash
uv python install
uv lock
uv sync --locked
```

`uv sync` creates `.venv` and installs the project in editable mode. The default
`dev` dependency group contains pytest, Ruff, mypy, and the PyYAML type stubs.

Commit the generated `uv.lock`. After that first bootstrap, a fresh checkout only
needs:

```bash
uv python install
uv sync --locked
```

Do not regenerate the lockfile implicitly in CI or when only validating an
existing checkout.

## Quality checks

Run the fast static checks first:

```bash
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
```

Then run the complete test suite locally:

```bash
uv run --locked pytest
```

For an intentional formatting change:

```bash
uv run ruff format .
uv run ruff check --fix .
```

Review the resulting diff before committing. Do not use `--fix` as part of a
read-only validation command.

## Lockfile maintenance

After intentionally changing dependencies in `pyproject.toml`:

```bash
uv lock
uv sync --locked
```

To update locked dependency versions without changing dependency declarations:

```bash
uv lock --upgrade
uv sync --locked
```

Always review and commit `pyproject.toml` and `uv.lock` together when dependency
metadata changes.

## Recommended local validation order

```bash
uv sync --locked
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv run --locked pytest
```

After these pass, run the live-source smoke tests described for each collector
before pushing the repository to GitHub. Scheduled GitHub Actions should be the
final environment validation, not the first place where local code quality
failures are discovered.

## Live smoke tests

Use an isolated runtime work root so collector state, items, derived data, and
reports never mix with the repository-tracked Action outputs:

```bash
export VRM_WORK_ROOT=.local/smoke
export GITHUB_TOKEN="$(gh auth token)"
TO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
FROM_2H="$(date -u -d '2 hours ago' +%Y-%m-%dT%H:%M:%SZ)"
FROM_24H="$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)"

uv run --locked python -m vision_research_monitor.cli.github_discovery \
  --from "$FROM_2H" \
  --to "$TO"

uv run --locked python -m vision_research_monitor.cli.link_items
uv run --locked python -m vision_research_monitor.cli.build_digest --date 2026-08-09
uv run --locked python -m vision_research_monitor.cli.build_trends --date 2026-08-09
uv run --locked python -m vision_research_monitor.cli.search_archive "gaussian splatting"

uv run --locked python -m vision_research_monitor.cli.openreview \
  --from "$FROM_24H" \
  --to "$TO"
```

Unset `VRM_WORK_ROOT` to return to the repository-tracked `data/` and `reports/`
layout used by GitHub Actions. `--work-root` can be supplied to one command when
a shell-wide environment override is not desired.

GitHub Discovery prints each search target to stderr and finishes with per-query
raw/accepted counts. OpenReview uses the official `openreview-py` API v2 client,
but current live smoke tests can require interactive challenge verification even
with the official client. Keep OpenReview as a local/manual diagnostic collector;
it is intentionally excluded from GitHub Actions until unattended access is reliable.
`OPENREVIEW_TOKEN`, or `OPENREVIEW_USERNAME` plus `OPENREVIEW_PASSWORD`, may still
be supplied for manual authenticated experiments.
