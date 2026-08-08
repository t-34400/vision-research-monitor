# Long-Term Analysis

**Status:** Active  
**Related tasks:** `TRD-001` through `TRD-005`  
**Related decisions:** `D-146` through `D-151`

## Purpose

Provide deterministic longitudinal analysis over canonical normalized items so
stored data can answer both daily-change and multi-day momentum questions.

## Inputs

The analyzer reads:

- `data/items/**/*.jsonl`;
- the regenerated Phase 4 entity graph;
- taxonomy configuration;
- `config/reporting.yaml` for timezone/day boundary;
- `config/analytics.yaml` for history and trend windows.

It does not call remote APIs and never mutates collector checkpoints.

## Time model

All longitudinal buckets use the same `Asia/Tokyo` 08:00 boundary as the daily
digest. A bucket named `2026-08-08` therefore represents:

```text
2026-08-07 08:00 JST <= discovered_at < 2026-08-08 08:00 JST
```

`discovered_at` is used instead of heterogeneous upstream publication/update
timestamps so historical monitoring reflects when the system actually observed
an item.

## Entity-aware aggregation

Raw item volume is retained, but topic and growth analysis uses Phase 4 logical
entity identities when available. A linked arXiv, OpenReview, and CVF record for
the same research work therefore contributes one logical entity rather than
three independent research works.

Records with `metadata.reportable = false` may participate in linking but are
excluded from trend activity counts.

Each daily bucket stores:

```text
date
items                 # raw reportable records
entities              # distinct logical entities active that day
new_repositories       # first-seen repository entities
new_papers             # first-seen paper entities
topics{}               # distinct active entities per topic
kinds{}                # raw records by kind
sources{}              # raw records by source
```

## Topic momentum

Configured rolling windows are compared with the immediately preceding window
of equal length. Phase 8 initially computes 7-day and 30-day windows.

For each topic:

```text
current_entities  = distinct logical entities with the topic in current window
previous_entities = distinct logical entities with the topic in previous window
```

To reduce false acceleration when total collection volume changes, momentum uses
Laplace-smoothed topic share rather than raw count ratio alone:

```text
current_share  = (current_entities + alpha) /
                 (current_total_entities + alpha * taxonomy_topic_count)
previous_share = (previous_entities + alpha) /
                 (previous_total_entities + alpha * taxonomy_topic_count)

momentum_score = log2(current_share / previous_share)
```

The raw count growth percentage is also preserved. A positive momentum score
means the topic's share of observed research entities increased relative to the
previous window.

## Repository and paper growth

Repository/paper growth uses the first observed timestamp of each logical
repository or paper entity. Linked duplicates count once.

The initial report compares the most recent seven days with the preceding seven
days. If the previous count is zero, percentage growth is recorded as `null`
rather than inventing an infinite percentage; the Markdown report labels that
case `new`.

## Recurring entities

Recurring activity is detected over a configurable 30-day lookback. An entity
must initially have at least:

- three reportable records; and
- activity on two distinct reporting days.

The result records the representative title/URL, active-day count, item count,
sources, kinds, topics, and latest observation time. Repository records are
preferred as representatives, followed by papers and other content kinds.

## Derived outputs

```text
data/analytics/YYYY-MM-DD.json
  deterministic daily buckets, topic momentum, growth, recurring entities

reports/trends/YYYY-MM-DD.md
  human-readable trend summary

data/archive/index.json
  compact searchable index of canonical records as of the latest built date
```

A historical manual rebuild creates its dated analytics/report output but does
not replace a newer archive index.

## Searchable archive

`python -m vision_research_monitor.cli.search_archive` searches the derived index
without a database or hosted service. It supports:

- free-text query;
- topic filters;
- source filters;
- kind filters;
- `--since` cutoff;
- optional hidden-record inclusion;
- bounded result limits.

The archive keeps each canonical record and its logical `entity_id`, allowing a
future static or database-backed UI to group records without changing the
canonical store.

## Dashboard strategy

Phase 8 deliberately does not add a hosted dashboard. The committed JSON archive
and analytics documents are the stable presentation-data boundary. A future
GitHub Pages/static client or external database/dashboard can consume that
boundary if interactive browsing becomes valuable enough to justify additional
operational surface.

## Automation

The existing daily digest workflow runs long-term analysis immediately after the
digest build and commits only allowlisted derived paths. It does not introduce a
second scheduled writer or a second repository-write concurrency slot.

## Failure behavior

- analytics/report writes are atomic;
- collector state is unaffected;
- a failed analytics build prevents the workflow commit for that run;
- historical backfills do not regress the current archive index;
- `.chatgpt-workspace-manifest.json` remains protected and unstaged.

## Acceptance criteria

- [x] daily topic/entity activity uses the digest time boundary;
- [x] linked paper/repository duplicates do not inflate unique growth;
- [x] 7-day and 30-day topic momentum is deterministic;
- [x] total corpus-volume changes are normalized in momentum scoring;
- [x] recurring entities are detected across distinct activity days;
- [x] repository and paper first-seen growth is reported;
- [x] a searchable derived archive is available without external infrastructure;
- [x] the scheduled daily workflow generates trend outputs automatically.
