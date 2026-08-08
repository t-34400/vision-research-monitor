# GitHub Watch Collector

**Status:** Active  
**Related tasks:** `GHW-001`–`GHW-013`  
**Related decisions:** `D-001`, `D-003`, `D-005`, `D-110`, `D-111`, `D-112`, `D-113`, `D-114`

## Purpose

Reliably detect changes from configured GitHub organizations, users, and
repositories without relying on GitHub search.

## API contract

The collector uses the GitHub REST API with an explicit API-version header.
Requests include a stable user agent, JSON media type, optional bearer token,
redirect following, bounded retries, and rate-limit handling.

Authentication precedence is:

1. `GH_WATCH_TOKEN`;
2. `GITHUB_TOKEN`;
3. unauthenticated public access.

A dedicated token is optional for public data but is recommended when the
built-in workflow token is insufficient for the target set or desired rate
budget.

## Account inventory

For each configured organization or user, the collector enumerates public owned
repositories using 100 records per page and compares GitHub repository IDs with
the previous inventory.

The inventory detects:

- newly observed repositories;
- stable-ID repository renames through snapshot comparison;
- meaningful repository metadata changes;
- repositories no longer listed under the watched account.

A missing repository is reported as `missing_from_account`, not asserted to be
deleted, because transfer and visibility changes can produce the same symptom.

## Repository detail collection

Detailed release/tag/default-branch checks run for:

- explicitly configured repositories on every watch run;
- account repositories whose GitHub snapshot indicates activity or metadata
  change;
- newly observed account repositories.

This avoids multiplying detail API calls across every repository in broad
organizations while still using direct account inventory for known-target
monitoring.

### Releases

Published non-draft releases are identified by GitHub release ID. The collector
retains recent seen release IDs and emits previously unseen releases.

If release history has not been initialized for an account repository, releases
newer than the repository's monitoring baseline may be emitted instead of
replaying historical releases.

### Tags

Tags are identified by repository ID plus tag name. Initial tag retrieval creates
a baseline without emitting historical tags. Subsequent previously unseen tags
are emitted.

Tag history is intentionally bounded to recent entries. The collector follows
additional pages while searching for a known tag, subject to a hard page limit.

### Default branch

The collector tracks the latest default-branch commit SHA. It emits the new head
when the SHA changes rather than replaying every intervening commit.

## Repository metadata events

Repository creation records preserve `homepage` in normalized metadata so later entity linking can use an explicit project/paper URL without re-fetching the repository.

The following fields are considered meaningful metadata for Phase 1:

- full name;
- description;
- homepage;
- topics;
- archived/disabled/fork state;
- visibility;
- default branch.

`updated_at` and `pushed_at` trigger detail checks but do not by themselves create
metadata events. Popularity counters are not metadata-change events.

## Bootstrap behavior

The first successful account inventory establishes a baseline and emits no
historical repository events.

Explicit repository detail checks also seed existing releases, tags, and branch
head without historical emission. If an endpoint fails during bootstrap, its
component remains uninitialized so a later successful run can recover from the
original observation time where timestamps permit it.

## Conditional requests

ETag/Last-Modified values are persisted in `http_cache` only after the
corresponding response has been successfully interpreted and its logical state
has been updated. This prevents a cached `304 Not Modified` from hiding data that
failed before checkpointing.

## Retry and rate-limit behavior

- transient 5xx responses use bounded exponential retry;
- `429` and recognized `403` rate-limit responses honor `Retry-After` or reset
  information when the wait is within the configured maximum;
- excessive waits fail the affected request instead of sleeping for an
  unbounded period;
- one failed target or detail endpoint does not erase successful results from
  other targets.

The command exits non-zero if any target/detail request failed, after writing
successful normalized items and state.

## Persistence and idempotency

State is stored at `data/state/github_watch.json`.

Normalized events are appended to date-partitioned `data/items/**/*.jsonl`.
Item IDs are deterministic from upstream identities or stable change
fingerprints. The item store scans existing IDs before appending so replay after
a failed checkpoint does not duplicate an already-written event.

State writes use atomic file replacement. Item output is written before state so
a failure cannot advance the checkpoint past data that was never persisted.

## Workflow

`.github/workflows/collect-github-watch.yml` runs at the cadence defined by
`610-scheduling.md` and supports manual dispatch.

The workflow serializes repository writes with the shared
`research-monitor-writes` concurrency group. It stages only `data/items` and
`data/state`; `.chatgpt-workspace-manifest.json` is explicitly checked and never
staged.

## Acceptance criteria

- organization and user repositories are enumerated with pagination;
- new repositories and meaningful metadata changes are detected;
- releases, tags, and default-branch head activity are tracked;
- initial runs do not flood historical data;
- transient API failures are retried within bounded limits;
- ETag-based conditional requests are supported;
- successful data survives unrelated target failures;
- repeated writes with the same event IDs remain idempotent;
- fixture-based tests cover API caching/retry, baseline/change behavior, tags,
  and storage deduplication;
- the protected workspace manifest remains byte-identical.
