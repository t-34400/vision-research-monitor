# Decision List

## Accepted

### D-001 — Separate collection paths by source semantics

**Status:** Accepted

Known-target monitoring, broad GitHub discovery, academic-source collection,
and later expanded sources have different recall/precision requirements and
checkpoint semantics. They remain separate collectors and workflows while
normalizing into the same downstream pipeline.

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
- arXiv: 01:37, 07:37, 13:37, 19:37;
- OpenReview: unscheduled; manual/local only per D-156;
- Hugging Face: 02:29, 08:29, 14:29, 20:29;
- CVF Open Access: 03:23;
- official research blogs: 03:31, 09:31, 15:31, 21:31;
- GitHub Discovery: 04:47, 16:47;
- Daily Digest: 08:11, using an 08:00 local reporting boundary.

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


### D-115 — Cover every taxonomy topic with explicit GitHub discovery queries

**Status:** Accepted

`config/github_discovery.yaml` groups repository-search queries by topic family,
and semantic validation requires every taxonomy topic to be referenced by at
least one query. Query wording can evolve independently from taxonomy labels.

### D-116 — Separate new-repository and active-repository discovery

**Status:** Accepted

Every normal topic query uses both bounded `created` and `pushed` searches.
`created` has no popularity floor so new research code can be found immediately;
`pushed` requires at least 10 stars initially to prevent broad mature-topic
queries from overwhelming the discovery stream.

### D-117 — Use overlapping bounded discovery checkpoints

**Status:** Accepted

The first run looks back 36 hours. Scheduled runs overlap the previous successful
checkpoint by two hours and permit at most 96 hours of automatic catch-up. A
staler checkpoint requires an explicit `--from` / `--to` backfill rather than
silently skipping history or launching an unbounded crawl.

### D-118 — Split dense GitHub searches by time instead of truncating

**Status:** Accepted

Each search slice may page through at most 1,000 results. If GitHub reports more
results than that capacity or marks results incomplete, the collector recursively
splits the UTC time range. A slice that remains unsafe at 15 minutes fails the
query and prevents checkpoint advancement.

### D-119 — Use deterministic lexical relevance before semantic classification

**Status:** Accepted

Topic-query evidence establishes a deterministic baseline and repository
name/description/topics can add stronger or additional taxonomy evidence.
Venue-only candidates receive no query-topic baseline and are gated by taxonomy
matches, with up to 100 README enrichments per run. Search requests are paced at
2.1 seconds to remain below the documented 30-request-per-minute repository
search limit.

### D-120 — Query arXiv by bounded submission windows

**Status:** Accepted

Phase 3 queries `cs.CV` and `cs.RO` independently with bounded `submittedDate`
ranges. Requests are paced at three seconds, arXiv version suffixes are removed
from normalized source identity, and cross-listed results are deduplicated by the
base arXiv ID before classification.

### D-121 — Configure OpenReview conference editions explicitly

**Status:** Accepted

Each monitored OpenReview edition declares its canonical venue ID, year, and
OpenReview `venueid` in `config/academic.yaml`. Runtime inference from conference
name strings is avoided because group identifiers are source-specific and
year-specific.

### D-122 — Bootstrap OpenReview editions before incremental discovery

**Status:** Accepted

The first successful run for each configured edition scans its public notes to
establish an inventory even when notes were created before deployment. Later
runs scan `tmdate:desc` and stop after crossing the overlapping checkpoint
window so modifications to older notes remain observable. The collector locally
applies the upper window boundary and fails rather than silently truncating page
overflow.

### D-123 — Keep academic relevance deterministic through Phase 3

**Status:** Accepted

Academic candidates use multi-label lexical matching over title, abstract, and
source keywords. The initial weights are 0.60, 0.30, and 0.35 respectively with
a minimum relevance score of 0.30. Semantic classification remains deferred to
Phase 6.

### D-124 — Keep arXiv and OpenReview checkpoints independent

**Status:** Accepted

Each source commits its own checkpoint only after successful item persistence.
Scheduled collection starts with a 48-hour lookback, overlaps by 180 minutes,
and allows 120 hours of automatic catch-up. Explicit backfills do not advance
the scheduled checkpoint.

### D-125 — Persist entity links as a derived sidecar

**Status:** Accepted

Phase 4 does not rewrite append-only normalized JSONL when new cross-source links
are discovered. It regenerates `data/entities/links.json` from canonical items
and materializes `related_items` at read time. This keeps collection history
stable while allowing linking rules to evolve.

### D-126 — Prefer exact external identifiers over fuzzy evidence

**Status:** Accepted

Base arXiv IDs, OpenReview note IDs, GitHub repository IDs/URLs, DOI values, and
canonical external URLs are the strongest Phase 4 evidence. GitHub release, tag,
commit, and repository events share the stable numeric repository ID extracted
from their source identity.

### D-127 — Require author support for paper title links

**Status:** Accepted

Normalized exact titles require at least 0.50 author overlap. Fuzzy title links
require at least 0.94 sequence similarity, 0.50 author overlap, and two shared
title tokens. Token blocks above 200 papers are skipped to prevent quadratic
candidate expansion. Title similarity or author overlap alone never links papers.
Thresholds live in `config/linking.yaml` so they can be evaluated and revised
without changing the algorithm contract.

### D-128 — Treat repository names as conservative supporting evidence

**Status:** Accepted

A repository-to-paper fallback link requires a distinctive repository name to
appear in the normalized paper title and at least one shared taxonomy topic.
Generic names such as `nerf`, `depth`, `slam`, `code`, and `project` are denied as
standalone evidence. Direct `related_items` preserve the actual accepted edges;
transitive entity membership does not invent pairwise evidence.


### D-129 — Rank with five independent deterministic signals

**Status:** Accepted

Phase 5 computes priority, relevance, freshness, novelty, and popularity
independently and persists all five in the daily ranking sidecar. The initial
weights are 0.30, 0.30, 0.15, 0.20, and 0.05 respectively, with a total-score
inclusion threshold of 0.35. Reweighting does not require recollection.

### D-130 — Preserve high-priority watch coverage in the digest

**Status:** Accepted

Items with explicit `priority.source >= 1.0` bypass the normal score threshold
and are rendered in an unlimited Priority Watch section. They still receive
normal ranking signals and a total score for explainability.

### D-131 — Use observed GitHub star growth as supporting popularity evidence

**Status:** Accepted

Phase 5 stores the positive star-count delta between GitHub watch snapshots and
maps it through a logarithmic popularity signal. Absolute star count does not
control ranking, and a star-only change does not emit a news item. First-time
discovery has no prior observation and therefore starts with zero delta.

### D-132 — Emit append-only OpenReview status-transition events

**Status:** Accepted

OpenReview note state records the last observed normalized status. Incremental
collection scans by descending true modification time; when a relevant note
changes status, a separate event records the previous and new status rather than
rewriting the canonical first-seen paper item. This makes later acceptance,
rejection, and withdrawal changes reportable without violating append-only item
storage.

### D-133 — Build the daily digest on an 08:00 Asia/Tokyo boundary

**Status:** Accepted

A digest date ends at 08:00 `Asia/Tokyo` and covers the preceding 24 hours by
`discovered_at`. The scheduled builder runs at 08:11 after the 07:37 arXiv slot.
Any manually collected OpenReview records before the boundary are included normally.
Entity links, per-day ranking JSON, and Markdown are derived from canonical normalized items.

### D-134 — Use a local semantic-profile TF-IDF model as the Phase 6 baseline

**Status:** Accepted

The default semantic classifier is `topic-profile-tfidf-v1`. Each taxonomy topic
has a curated profile composed of its label, aliases, and descriptive hints. The
classifier uses deterministic word/character n-gram TF-IDF cosine similarity and
requires no model download, hosted API, or new runtime dependency. This provides
an auditable semantic-similarity baseline before introducing learned embeddings.

### D-135 — Run semantic classification only after source-level candidate reduction

**Status:** Accepted

Semantic classification never broadens source crawling or GitHub Search. GitHub
repositories must first come from configured search/venue discovery, arXiv papers
must come from configured categories and bounded windows, OpenReview papers must
come from configured editions, and expanded-source candidates must first come
from their configured CVF inventories, Hub queries, or official feeds. Lexical
classification runs first; semantic scoring can recover low-lexical candidates or
conservatively enrich labels on an already accepted lexical candidate.

### D-136 — Persist classifier evidence without changing the common item schema

**Status:** Accepted

Final topics remain in `topics` and final relevance remains in
`scores.relevance`. New records store classification provenance under
`metadata.classification`, including the method, lexical score, semantic model
ID, semantic similarity/per-topic scores, and optional LLM model/reason. This
keeps downstream ranking independent from classifier implementation details.

### D-137 — Keep hosted LLM classification optional and provider-neutral

**Status:** Accepted

Phase 6 defines an `LLMTopicClassifier` contract but does not select or require a
hosted provider. An LLM may be invoked only for lexically insufficient candidates
that already have a bounded semantic topic shortlist and whose semantic score is
inside a configured ambiguity range. Collection must still succeed with no LLM
provider configured.

### D-138 — Reuse the common pipeline for expanded-source item kinds

**Status:** Accepted

Phase 7 adds `model` and `article` item kinds and uses the existing `project` kind
without introducing source-specific downstream models. CVF, Hugging Face, and
official-feed records still use the same normalization, classification, linking,
ranking, persistence, and reporting stages.

### D-139 — Treat CVF proceedings pages as guarded inventories

**Status:** Accepted

Configured CVF Open Access proceedings pages are polled as inventories because
they do not provide the same bounded timestamp API as arXiv/OpenReview. The first
successful run baselines existing paper IDs without emitting historical papers.
Later unseen IDs are fetched and classified. An edition-specific minimum paper
count and a requirement that previously observed paper IDs remain present prevent
a partial page or upstream HTML change from replacing a complete inventory.

### D-140 — Discover Hugging Face model repositories by bounded modification time

**Status:** Accepted

The Phase 7 Hugging Face scope is public model repositories. Configured Hub
searches are sorted by descending `lastModified` and paged until the bounded
collection window is crossed. Candidate repositories are deduplicated across
queries by repository ID and unchanged `repo_id@lastModified` revisions are not
re-emitted. A bounded number of model cards can enrich low-lexical candidates.
Spaces and datasets remain out of scope for this phase. Hub requests are paced at
0.75 seconds initially and retain bounded 429 retry handling because anonymous
rate limits can be lower and vary over time.

### D-141 — Preserve source-declared project and code relationships explicitly

**Status:** Accepted

When a source page explicitly provides project/code URLs, collectors preserve
those URLs in allowlisted metadata. A CVF project-page sidecar can additionally
declare its parent paper through `related_items`; the linker records that
source-declared edge as exact `explicit_relation` evidence rather than attempting
to rediscover it fuzzily. List-valued URL metadata participates in exact linking.

### D-142 — Give expanded sources dedicated low-noise reporting behavior

**Status:** Accepted

CVF papers reuse paper sections, Hugging Face models use `Models & Demos`, and
official research posts use `Research Announcements`. Expanded-source default
priorities remain modest so source prestige alone does not establish importance.
Relationship-only project sidecars carry `metadata.reportable = false`; they
can enrich linking and parent-paper links but never render as duplicate headlines.

### D-143 — Monitor only stable official research feeds initially

**Status:** Accepted

Phase 7 starts with official RSS/Atom feeds from Google Research, Microsoft
Research, and Apple Machine Learning Research. Feed publication alone is not a
topic match: title, summary/content, and categories go through the same lexical
and semantic relevance pipeline. Official sites without a stable configured
feed are not scraped generically.

### D-144 — Defer a generic individual-researcher crawler

**Status:** Accepted

No broad personal-site crawler is introduced in Phase 7. Researcher pages have
inconsistent update semantics and no curated high-value researcher list has been
specified. A researcher source should be added later only when it has a stable
machine-readable feed/API or is explicitly promoted to a high-value watch target.

### D-145 — Stagger expanded-source workflows away from the pre-digest cluster

**Status:** Accepted

New source workflows share the repository-write concurrency group with existing
collectors, but their schedules are intentionally spread across otherwise quiet
periods. Hugging Face runs every six hours at `:29`, CVF daily at 03:23 JST, and
research feeds every six hours at `:31` on alternating hours. This reduces the
chance of multiple pending writers around the 07:37 academic collection and
08:11 digest sequence.

### D-146 — Align longitudinal buckets with the daily digest boundary

**Status:** Accepted

Long-term analytics use `discovered_at` and the same Asia/Tokyo 08:00 reporting
boundary as the daily digest. This keeps "today" consistent across daily reports
and trend history while avoiding incomparable upstream timestamp semantics.

### D-147 — Measure topic momentum with entity-normalized share change

**Status:** Accepted

Topic momentum compares distinct logical entities in equal rolling windows.
The score is the base-2 logarithm of Laplace-smoothed current topic share over
previous topic share. Raw counts and count growth remain visible, but share-based
momentum reduces false acceleration when overall collection volume changes after
new sources are added.

### D-148 — Define repository/paper growth by first-seen logical entities

**Status:** Accepted

Repository and paper growth count the first observation of each Phase 4 logical
entity. Multiple records for one work across arXiv, OpenReview, CVF, or GitHub do
not multiply the growth count. Zero previous volume is represented as a new
baseline rather than infinite percentage growth.

### D-149 — Separate recurring activity from new-entity growth

**Status:** Accepted

Recurring entities are a distinct signal: initially at least three reportable
records across at least two reporting days in a 30-day lookback. This surfaces
projects or research entities with sustained activity without treating repeated
updates as newly created research.

### D-150 — Use a derived searchable archive before adding a hosted dashboard

**Status:** Accepted

Phase 8 generates `data/archive/index.json` and a local search CLI with text,
topic, source, kind, and time filters. The index preserves logical entity IDs and
is a stable future UI boundary. A hosted dashboard or external database remains
deferred until archive size or interactive-use requirements justify the added
operational complexity.

### D-151 — Build trends in the existing daily reporting workflow

**Status:** Accepted

Long-term analytics run after the daily digest in the existing 08:11 JST
workflow and share its repository-write concurrency. This avoids a second daily
writer while keeping analytics failure isolated from collector checkpoints. The
workflow stages only explicit derived-data/report paths and never stages the
workspace manifest.

### D-152 — Standardize local development on uv

**Status:** Accepted

Local Python setup, dependency resolution, locking, and command execution use uv.
Python 3.13 is pinned through `.python-version`, while `pyproject.toml` declares
the supported `>=3.13,<3.14` range. Development tools live in the PEP 735 `dev`
dependency group. `uv.lock` is committed after generation in a network-enabled
environment; subsequent validation uses `--locked` so local and CI dependency
resolution cannot drift silently. Existing GitHub Actions may continue using the
current install path until that lockfile is generated and validated locally.

### D-153 — Match OpenReview official-client request identity for guest API access

**Status:** Superseded by D-155

OpenReview API v2 collection keeps the existing bounded HTTP/pagination logic,
but sends an OpenReview-compatible `User-Agent` matching the official
`openreview-py` client format. Live guest requests using the generic project
User-Agent returned HTTP 403 through the challenge endpoint, while OpenReview's
official client identifies itself explicitly. `OPENREVIEW_TOKEN` remains an
optional Bearer token rather than a required credential for public notes.

### D-154 — Require metadata corroboration for broad GitHub discovery queries

**Status:** Accepted

A GitHub Search hit is candidate-generation evidence, not sufficient relevance
evidence. Normal topic searches use repository name, description, and topics;
README-wide search is reserved for venue/year discovery. Query evidence is weak,
`pushed` discovery requires at least 50 stars, forks are excluded, and generic
ML/data terms require explicit vision context unless an unrestricted query also
surfaced the repository. Per-query raw and accepted counts are emitted to make
future threshold tuning measurable.

### D-155 — Use the official OpenReview API v2 Python client

**Status:** Accepted

OpenReview collection uses `openreview-py` and `openreview.api.OpenReviewClient`
for API v2 reads. A second live smoke test showed that imitating the official
User-Agent with the generic HTTP client still returned HTTP 403 for every
configured venue. The collector keeps its bounded paging, modification-ordered
scan, checkpoint, and status-transition logic, but delegates transport, request
identity, authentication, and 429/5xx retry behavior to the official client.
Guest access is the default; bearer-token or username/password authentication
remains optional.

## Future decisions

The following choices remain intentionally deferred until measured operational
need justifies them:

- whether a hosted embedding/LLM provider adds enough measured value beyond the provider-neutral Phase 6 contract;
- when repository-tracked canonical history is large enough to justify external storage;
- whether interactive archive usage justifies a hosted dashboard beyond the Phase 8 search index/CLI.
