# Runtime Work Root

**Status:** Active  
**Related tasks:** `STB-007`  
**Related decisions:** `D-157`

## Purpose

Separate local smoke-test output from the repository-tracked runtime data written
by scheduled GitHub Actions without maintaining two path configurations.

## Default layout

When no override is supplied, runtime paths remain unchanged:

```text
<data repository root>/
├── data/
│   ├── items/
│   ├── state/
│   ├── entities/
│   ├── ranking/
│   ├── analytics/
│   └── archive/
└── reports/
    ├── daily/
    └── trends/
```

This is the canonical GitHub Actions layout and remains eligible for explicit
workflow staging and commits.

## Local override

Every runtime CLI accepts `--work-root`. The same value can be supplied through
`VRM_WORK_ROOT`. A relative work root is resolved from the repository root, not
from an arbitrary process working directory.

For example:

```bash
export VRM_WORK_ROOT=.local/smoke
```

maps runtime output to:

```text
.local/smoke/
├── data/
│   ├── items/
│   ├── state/
│   ├── entities/
│   ├── ranking/
│   ├── analytics/
│   └── archive/
└── reports/
    ├── daily/
    └── trends/
```

`.local/` is ignored by Git, so local collection, linking, reporting, analytics,
and archive-search smoke tests do not dirty repository-tracked production data.

## Precedence

Path selection follows this order:

1. an explicit command-specific path such as `--items`, `--state`, or `--output`;
2. `--work-root`;
3. `VRM_WORK_ROOT`;
4. the repository root.

Command-specific path overrides are retained for targeted debugging. Configuration
files under `config/` are not redirected by the runtime work root.

## Actions behavior

Scheduled workflows do not set `VRM_WORK_ROOT` or `--work-root`. Their paths
therefore remain `data/**` and `reports/**`, preserving existing staging and
persistence behavior.
