# Persistence and Retention

**Status:** Active  
**Related tasks:** `FND-015`  
**Related decisions:** `D-008`, `D-101`, `D-107`, `D-125`

## Purpose

Define the initial durable storage model and retention policy for a
GitHub-Actions-first deployment.

## Canonical storage

The initial canonical store is version-controlled repository data:

```text
data/
  items/
    YYYY/
      MM/
        DD.jsonl
  entities/
    links.json
  ranking/
    YYYY-MM-DD.json
  analytics/
    YYYY-MM-DD.json
  archive/
    index.json
  state/
    <collector>.json
reports/
  daily/
    YYYY-MM-DD.md
  trends/
    YYYY-MM-DD.md
```

Normalized items use append-friendly JSONL partitioned by UTC discovery date.
Collector state is explicit mutable JSON. Entity-link output is a derived JSON
sidecar that can be regenerated from normalized items. Per-day ranking and
analytics documents, the searchable archive index, and daily/trend Markdown
reports are also derived outputs.

The storage abstraction may migrate later, but collectors and normalized item
semantics must not depend on Git as a database-specific API.

## Retention

- normalized items: retained indefinitely unless a future storage migration
  changes the policy;
- entity-link sidecar: retained as the current derived graph and freely regenerable;
- per-day ranking and analytics sidecars: retained with the corresponding reports and freely regenerable;
- searchable archive index: only the latest derived index is required;
- daily and trend reports: retained indefinitely;
- collector state/checkpoints: only the current state is required canonically;
- raw upstream API responses: not committed by default;
- short-lived diagnostic artifacts: non-canonical and should use a short CI
  retention period when introduced.

## Checkpoint safety

Collector state must advance only after its corresponding normalized output is
durably written. A failed run must be replayable from the previous committed
checkpoint.

## Concurrent automation

Workflows that write canonical data must serialize repository writes or use an
explicit conflict-safe strategy. Automated commits must stage only expected data,
state, and report paths rather than staging the entire working tree.

## Workspace metadata

`.chatgpt-workspace-manifest.json` is outside the application persistence model
and must never be created, edited, staged, regenerated, or deleted by collection
or reporting automation.

## Migration

If repository growth becomes operationally expensive, move canonical data to an
external/object storage backend behind the persistence boundary. Such a migration
requires a new architectural decision and a reproducible export/import path.


## Runtime root

Canonical Action output uses the repository root. Local smoke tests may mirror the same `data/**` and `reports/**` layout beneath an isolated work root as defined in `540-runtime-work-root.md`.
