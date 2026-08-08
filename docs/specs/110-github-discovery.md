# GitHub Discovery

**Status:** Active  
**Related tasks:** `GHD-001` through `GHD-010`  
**Related decisions:** `D-001`, `D-003`, `D-004`, `D-115`, `D-116`, `D-117`, `D-118`, `D-119`, `D-134`, `D-135`

## Purpose

Discover relevant public GitHub repositories that are not already known watch
targets. Discovery favors recall during candidate generation while keeping the
collection window, API cost, and downstream candidate volume bounded.

## Configuration

`config/github_discovery.yaml` is validated by
`config/schemas/github-discovery.schema.json`.

The configuration owns:

- collection-window and catch-up limits;
- GitHub Search pagination and pacing;
- lexical relevance thresholds;
- one or more search queries grouped into topic query families;
- optional per-query `created` / `pushed` modes;
- venue/year README discovery;
- the README-enrichment cap used for venue-only candidates.

Every taxonomy topic must be referenced by at least one configured topic query.
Unknown topic or venue IDs are rejected during configuration loading.

## Discovery paths

### Topic discovery

Each configured query is executed against repository name, description, topics,
and README content using two independent modes unless a query overrides them:

- `created` finds repositories created during the bounded collection window;
- `pushed` finds existing repositories pushed during the bounded collection
  window.

`pushed` queries apply a minimum-star qualifier. Newly created repositories do
not require stars because they are covered independently by `created` queries.

Public, non-archived repositories are the initial discovery scope. Forks remain
excluded by GitHub repository-search defaults unless the configuration is later
changed deliberately.

### Venue/year discovery

Core venues are expanded using the configured year offsets relative to the
current `Asia/Tokyo` year. The collector searches for strings such as
`"CVPR 2026" in:readme` using the same bounded `created` and `pushed` modes.

A venue match alone does not establish topical relevance. Venue-only candidates
must match the research taxonomy through repository metadata or a bounded README
enrichment request.

## Collection windows and checkpoints

The initial run searches a trailing lookback window. Later automatic runs start
from the last successful checkpoint minus an overlap interval and end at the
current run timestamp.

The checkpoint advances only after:

1. all configured discovery searches completed without query failures; and
2. normalized items were passed to the durable item store.

If the last successful checkpoint is older than the configured maximum catch-up
window, automatic collection fails explicitly. Operators can use `--from` and
`--to` for an explicit bounded backfill; manual backfills do not move the normal
scheduled checkpoint.

## Search result completeness

Repository Search is paginated at up to 100 results per page. A search slice has
a configured page capacity.

When GitHub reports more results than the slice can safely page, or marks the
result incomplete, the collector recursively divides the time window and repeats
the search. If a still-dense slice reaches the minimum allowed time width, the
query fails and the scheduled checkpoint is not advanced.

Repository IDs deduplicate results produced by overlapping windows, multiple
query families, multiple modes, and split search slices.

## Search pacing

GitHub repository search has a dedicated rate-limit resource. Search requests
are issued serially with a configured minimum interval. Normal GitHub REST retry
and rate-limit handling remains active as a second line of defense.

README enrichment uses the normal REST API resource, is attempted only when
needed for venue-only topical gating, and has a per-run cap.

## Relevance classification

Phase 2 established deterministic lexical scoring as the baseline.

Evidence is drawn from:

- the topic query that surfaced the repository;
- repository name/full name;
- repository description;
- GitHub topics;
- README text when venue-only enrichment is required.

Topic-query evidence gives a candidate a baseline relevance score. Direct
metadata matches can raise that score and add additional taxonomy topics. Venue
candidates have no topic-query baseline and must independently match at least one
taxonomy topic.

From Phase 6 onward, a candidate that does not pass the configured lexical
threshold may be evaluated by the local semantic-profile classifier. This does
not broaden GitHub Search itself: semantic classification runs only after the
repository has already been surfaced by a configured topic query or venue/year
search. Accepted lexical candidates may also receive conservative semantic
multi-label enrichment.

The normalized item stores final relevance under `scores.relevance` and records
classification method/model evidence in `metadata.classification`.

## Normalized output

A discovered repository uses the same stable identity as a repository discovered
through GitHub Watch:

```text
id        = github:repository:<repository-id>
source    = github
source_id = <repository-id>
kind      = repository
```

This lets the JSONL store naturally suppress duplicates when Watch and Discover
observe the same repository.

Discovery-specific metadata includes:

- discovery modes;
- query IDs and query-family IDs;
- venue/year hits;
- GitHub topics;
- repository homepage;
- stars and forks;
- primary language;
- fork/archive flags.

## Failure behavior

A failed topic or venue query is reported as a structured diagnostic and prevents
checkpoint advancement. Successful candidates from the same run may still be
persisted. Retrying the window is safe because normalized repository IDs are
stable and the item store is idempotent.

README failures are warnings rather than collection failures. A venue-only
candidate without enough topical evidence is skipped.

## Acceptance criteria

- [x] Every taxonomy topic has at least one configured discovery query.
- [x] `created` and `pushed` discovery use explicit UTC time windows.
- [x] Venue/year README searches are generated from the venue registry.
- [x] Dense or incomplete searches split their time windows instead of silently truncating.
- [x] Scheduled checkpoints advance only after a fully successful search run.
- [x] Candidates receive deterministic lexical relevance scores and multi-label topics.
- [x] Discovered repositories normalize to the shared item model.
- [x] Fixture-based tests cover aggregation, splitting, README enrichment, and stale checkpoints.
