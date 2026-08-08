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
