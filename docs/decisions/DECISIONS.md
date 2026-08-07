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
their normal ranking score would be low. Event significance rules may still
suppress low-value commit noise.

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

### D-101 — Use repository-tracked JSONL and explicit state initially

**Status:** Accepted

The initial durable store uses date-partitioned JSONL for normalized items and
explicit JSON files for collector checkpoints. Markdown reports are derived from
that canonical data. The persistence boundary must permit later migration to
object storage or a database without changing collector contracts.

### D-102 — Publish the initial digest as committed Markdown

**Status:** Accepted

The initial report target is `reports/daily/YYYY-MM-DD.md` committed with the
canonical data. GitHub Pages and external notification channels are deferred
until the underlying digest is stable.

### D-103 — Use staggered scheduled collection

**Status:** Accepted

Initial `Asia/Tokyo` schedules are:

- GitHub Watch: 00:17, 06:17, 12:17, 18:17;
- Academic: 01:37, 07:37, 13:37, 19:37;
- GitHub Discovery: 04:47, 16:47;
- Daily Digest: 00:27, summarizing the previous local calendar day.

Cron expressions are stored in UTC and avoid top-of-hour execution.

### D-104 — Start with a small explicit GitHub watchlist

**Status:** Accepted

The initial watchlist is defined in `config/github_watchlist.yaml`. It covers
Google research organizations, Microsoft, NVIDIA research organizations, Meta
research, and nerfstudio projects. Broad organizations require topic filtering
where appropriate, while research-focused targets can receive high priority.

### D-105 — Start with cross-domain venues centered on vision and 3D

**Status:** Accepted

The initial registry in `config/venues.yaml` treats CVPR, ICCV, ECCV, WACV, 3DV,
SIGGRAPH/SIGGRAPH Asia, ICRA, IROS, and CoRL as core sources, with major ML and
XR venues included as secondary sources.

### D-106 — Defer semantic-classification provider selection until Phase 6

**Status:** Accepted

No embedding or LLM provider is selected during the collection phases. The
collector and normalized-item contracts must remain provider-independent. A
provider is chosen only after a deterministic baseline and evaluation set exist.

### D-107 — Retain normalized history and reports, not raw API payloads

**Status:** Accepted

Normalized items and daily reports are retained indefinitely under the initial
repository-backed store. Only current collector state is required canonically.
Raw upstream responses are not committed by default; diagnostic CI artifacts are
short-lived and non-canonical.

### D-108 — Use Asia/Tokyo for reporting and UTC for storage

**Status:** Accepted

Persisted timestamps and checkpoints use UTC. Human-facing daily boundaries and
digest dates use `Asia/Tokyo`.

### D-109 — Use YAML configuration validated by JSON Schema

**Status:** Accepted

Human-edited taxonomy, watchlist, and venue registries use YAML. Their structural
contracts are versioned JSON Schema files under `config/schemas/`. Cross-file
references such as repository topic IDs require an additional semantic
validation step because JSON Schema alone cannot enforce them cleanly.

### D-110 — Treat the first GitHub watch run as a baseline

**Status:** Accepted

Initial account inventories and direct-repository detail scans seed state without
emitting historical repository, release, tag, or commit activity. Timestamped
activity that occurs after monitoring began can still be recovered if a detail
endpoint was temporarily unavailable.

### D-111 — Inventory accounts directly and detail only active repositories

**Status:** Accepted

Every watched account is enumerated directly through the account repository API.
Release/tag/default-branch detail calls are limited to explicitly watched
repositories and account repositories that are new or whose repository snapshot
changed. This preserves direct monitoring while controlling API cost for broad
organizations.

### D-112 — Represent default-branch activity by head transitions

**Status:** Accepted

Phase 1 tracks the latest default-branch SHA and emits head changes rather than
materializing every commit between scheduled runs. Full commit history can be
added later if a concrete reporting need justifies the volume.

### D-113 — Commit HTTP validators only after logical processing succeeds

**Status:** Accepted

ETag and Last-Modified validators are persisted only after the caller has
successfully interpreted a response and updated the related logical state. This
prevents a later 304 response from masking data that was fetched but never
checkpointed.

### D-114 — Pin the GitHub REST API version

**Status:** Accepted

Phase 1 sends `X-GitHub-Api-Version: 2026-03-10`. API-version changes are explicit
maintenance work and must be validated against the GitHub collector tests and
source documentation before updating the pin.

## Future decisions

The following choices are intentionally deferred until their roadmap phases:

- discovery query weighting and candidate thresholds (Phase 2);
- source-specific venue edition resolution (Phase 3);
- fuzzy entity-link thresholds (Phase 4);
- ranking weights and digest cutoffs (Phase 5);
- semantic provider/model and evaluation threshold (Phase 6);
- external storage or dashboard migration triggers (Phase 7/8).
