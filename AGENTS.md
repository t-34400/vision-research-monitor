# Project Rules

This file is the canonical source for project-wide implementation rules.

## 1. Project goal

Build an automated research-information collection pipeline for computer vision,
3D vision, robotics perception, embodied vision, and adjacent topics.

The system must support:

- reliable monitoring of known GitHub users, organizations, and repositories;
- discovery of previously unknown repositories;
- collection of papers and conference information;
- normalization, deduplication, classification, ranking, and reporting;
- future addition of new sources without redesigning the core pipeline.

## 2. Architectural rules

1. Keep **Watch**, **Discover**, and **Academic** collection paths separate.
   They have different recall, precision, and update semantics.
2. All collectors must emit the same normalized item model.
3. Topic definitions, watchlists, venues, and discovery queries must be
   configuration-driven. Do not hard-code them in collector logic.
4. Collectors collect facts. Classification, deduplication, ranking, and
   reporting belong to later pipeline stages.
5. Prefer idempotent processing. Re-running the same collection window must not
   create duplicate logical items.
6. Preserve source identifiers and source URLs so every normalized item is
   traceable to its origin.
7. Store timestamps in UTC internally. Convert to the reporting timezone only
   at presentation boundaries.
8. Treat source data as untrusted. Validate required fields at the normalization
   boundary, not with source-specific assumptions spread through the codebase.
9. Prefer conservative entity linking. Link uncertain matches as related items
   rather than destructively merging them.
10. Keep ranking signals separate. Do not persist only one opaque total score.

## 3. Collection rules

- Known high-priority watch targets must be collected directly rather than
  rediscovered through search.
- GitHub discovery queries must use bounded time windows.
- State such as cursors, last-seen timestamps, ETags, and source checkpoints must
  be explicit and recoverable.
- Use conditional requests where supported.
- Respect API rate limits and back off on transient failures.
- A failure in one source must not invalidate successfully collected data from
  unrelated sources.
- Do not silently discard malformed or unclassified candidates. Record enough
  diagnostics to understand why an item was skipped.

## 4. Classification and ranking rules

- Phases 1-3 use deterministic rules first. Semantic or LLM classification is a
  later enhancement, not a prerequisite for collection.
- A watched high-priority source can bypass normal ranking thresholds.
- Relevance and importance are different concepts and must be represented
  separately.
- Popularity must not dominate new research. Prefer deltas and freshness over
  absolute star counts when measuring momentum.
- Topic assignment may be multi-label.

## 5. Data and persistence rules

- GitHub Actions artifacts and logs are not the canonical long-term datastore.
- Persist enough normalized data and state to reproduce daily reports.
- Prefer append-friendly records for collected items and explicit mutable state
  for cursors/checkpoints.
- Schema changes must be documented in `docs/specs/` and, when architectural,
  in `docs/decisions/`.

## 6. GitHub Actions rules

- Keep collection workflows source-oriented and small.
- Avoid scheduling all workflows at the top of the hour.
- Secrets must come from GitHub Actions secrets or environment configuration.
  Never commit tokens.
- Workflows should expose useful failure context without leaking secrets.
- A workflow should be restartable without manual cleanup.

## 7. Development environment

- Use `uv` as the project Python environment and dependency manager.
- `.python-version` is the canonical local Python minor-version request.
- Declare runtime and development dependencies in `pyproject.toml`; do not add parallel requirements files unless an external integration requires one.
- Commit `uv.lock` once it has been generated from a network-enabled environment, and use `uv sync --locked` / `uv run --locked` for reproducible validation thereafter.
- Do not use `pip install` or an independently managed virtual environment for normal project development.
- Run Ruff formatting check, Ruff lint, mypy, then pytest before the first GitHub push and before dependency/tooling changes are accepted.

## 8. Testing rules

- Unit-test normalization, matching, deduplication, state transitions, and
  ranking logic with local fixtures.
- Avoid live-network tests in the normal test suite.
- Give each collector contract tests using captured/minimal fixtures.
- Add regression fixtures when fixing parsing or normalization bugs.
- Prefer targeted validation during development; broad integration tests should
  be deliberate rather than the default.

## 9. Workspace metadata protection

- `.chatgpt-workspace-manifest.json` is managed externally as a workspace management tag.
- Never create, edit, reformat, regenerate, delete, rename, or otherwise modify `.chatgpt-workspace-manifest.json`.
- Preserve that file exactly when modifying, packaging, or exporting the repository.
- Automation that creates commits must stage explicit allowlisted paths and must never stage `.chatgpt-workspace-manifest.json`.

## 10. Documentation rules

- `ROADMAP.md` describes sequencing and phase outcomes.
- `TASKS.md` contains executable work items and their status.
- `docs/specs/` defines current intended behavior.
- `docs/decisions/DECISIONS.md` records architectural/product decisions and open
  decisions.
- When behavior changes, update the relevant spec in the same change.
- When a choice changes architecture or long-term conventions, update the
  decision list in the same change.

## 11. Definition of done

A task is done only when:

- implementation and relevant configuration are complete;
- targeted tests or validation cover the changed behavior;
- failure behavior is defined;
- relevant specs are updated;
- affected decision entries are updated when applicable;
- no temporary debug output, secrets, or local-only paths remain.
