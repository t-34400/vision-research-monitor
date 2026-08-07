# Decision List

## Accepted

### D-001 — Separate Watch, Discover, and Academic collection paths

**Status:** Accepted

Known-target monitoring, broad GitHub discovery, and academic-source collection
have different recall/precision requirements and checkpoint semantics. They are
separate collectors and workflows.

### D-002 — Use one normalized item model across sources

**Status:** Accepted

GitHub records, papers, releases, and future sources normalize into a shared
record shape so downstream linking, classification, ranking, and reporting do
not depend on source-specific schemas.

### D-003 — Keep taxonomy and watch targets configuration-driven

**Status:** Accepted

Topics, aliases, organizations, repositories, venues, and discovery queries
belong in configuration, not hard-coded collector logic.

### D-004 — Establish deterministic collection before semantic classification

**Status:** Accepted

Initial phases use source APIs and lexical/configuration rules. Embeddings or
LLMs are introduced after collection coverage and baseline filtering can be
measured.

### D-005 — High-priority watch targets bypass normal ranking thresholds

**Status:** Accepted

Updates from explicitly configured high-priority sources are included even if
their normal ranking score would be low.

### D-006 — Persist ranking signals separately

**Status:** Accepted

Priority, relevance, freshness, novelty, and popularity are stored as distinct
signals. A combined presentation score may be computed later.

### D-007 — Prefer conservative linking over aggressive merging

**Status:** Accepted

Exact identifiers and URLs are used first. Ambiguous paper/repository matches
are connected through `related_items` unless evidence is strong enough to merge.

### D-008 — GitHub Actions artifacts are not canonical storage

**Status:** Accepted

Artifacts/logs may be used for diagnostics or temporary outputs but not as the
only long-term source of collected data or state.

## Proposed / Open

### D-101 — Canonical persistence backend

**Status:** Proposed

Choose the initial durable persistence model.

Candidates:

- versioned JSONL/state files committed to the repository;
- SQLite committed or published separately;
- GitHub Releases / object storage;
- external database.

The first implementation should prefer simplicity but must support deterministic
rebuilds and safe checkpointing.

### D-102 — Daily report publication target

**Status:** Proposed

Choose whether reports are:

- committed Markdown only;
- published through GitHub Pages;
- delivered to an external notification channel;
- some combination of the above.

### D-103 — Collection cadence

**Status:** Proposed

Choose the exact schedules for:

- GitHub Watch;
- GitHub Discovery;
- academic collection;
- daily digest.

Avoid top-of-hour schedules.

### D-104 — Initial watchlist

**Status:** Proposed

Finalize the first organizations/users/repositories and their priority levels.
The initial candidate set includes major research organizations and projects
already discussed, but the concrete configuration should be reviewed before
implementation.

### D-105 — Initial venue set

**Status:** Proposed

Finalize the initial academic/conference venue set and distinguish core venues
from optional broader ML/robotics venues.

### D-106 — Semantic classification provider

**Status:** Proposed

Defer provider/model selection until Phase 6. The collector contracts must not
depend on this choice.

### D-107 — Retention and history policy

**Status:** Proposed

Decide how long raw normalized items, repository snapshots, and detailed change
history are retained.

### D-108 — Report timezone

**Status:** Proposed

Store UTC internally. Choose the explicit display/report timezone before
scheduling the daily digest.
