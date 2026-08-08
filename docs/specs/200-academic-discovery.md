# Academic Discovery

**Status:** Active  
**Related tasks:** `ACA-001` through `ACA-008`  
**Related decisions:** `D-120`, `D-121`, `D-122`, `D-123`, `D-124`

## Purpose

Collect relevant academic papers independently of GitHub repository publication
and normalize them into the same item model used by repository collectors.

## Sources

Phase 3 supports:

- arXiv API for category-based recent-paper discovery;
- OpenReview API v2 for configured conference editions.

Source configuration lives in `config/academic.yaml` and is validated by
`config/schemas/academic.schema.json`.

## Common relevance filter

Academic candidates are matched against the project taxonomy using title,
abstract, and source keywords where available.

The initial deterministic weights are:

- title: `0.60`;
- abstract: `0.30`;
- keywords: `0.35`;
- minimum relevance: `0.30`.

Topic classification is multi-label. Semantic classification remains deferred to
Phase 6.

## arXiv

### Query scope

Each configured arXiv category is queried independently. The initial categories
are `cs.CV` and `cs.RO`.

Queries use a bounded `submittedDate` range and ascending submission order.
Request pages contain at most 200 entries and requests are paced by the configured
3-second interval.

### Identity

Version suffixes such as `v2` are removed from the normalized source identity:

```text
arxiv:paper:2608.01234
```

The versioned identifier remains in metadata. Cross-listed results from multiple
categories are combined before normalization.

### Metadata

Preserve when available:

- authors;
- categories and primary category;
- arXiv comment;
- journal reference;
- DOI;
- PDF URL;
- publication and update timestamps.

Venue inference from arXiv text is conservative and uses configured venue aliases.

## OpenReview

### Editions

OpenReview conference editions are explicit configuration records containing:

```text
canonical venue ID
conference year
OpenReview venue ID
```

Phase 3 does not infer edition IDs from venue names at runtime.

### Bootstrap and incremental discovery

For an edition without a bootstrap marker, the collector scans all public notes
for that configured `venueid`. This establishes the relevant-paper inventory even
when the original note creation predates deployment.

After bootstrap, collection uses `mintcdate` from the overlapping source window
and locally enforces the upper window boundary. A page limit is a hard coverage
failure rather than a silent truncation.

### Status normalization

OpenReview notes normalize to:

- `withdrawn` when the venue label indicates withdrawal;
- `rejected` when the venue label indicates rejection;
- `accepted` when `pdate` is present;
- `submitted` otherwise.

The current status is stored in item metadata. Phase 3 treats a normalized paper
as first-seen discovery data; durable status-transition events for an already
stored note are implemented before Phase 5 change labels are generated.

### Identity

```text
openreview:paper:<note-id>
```

The stable note ID remains `source_id`. The normalized `venue` field uses the
canonical venue registry ID rather than the OpenReview group string.

## Checkpoints

arXiv and OpenReview use independent state files and independent successful-run
checkpoints.

Initial automated lookback is 48 hours, scheduled windows overlap by 180 minutes,
and automatic catch-up is capped at 120 hours. A stale checkpoint requires an
explicit `--from` / `--to` backfill.

Manual backfills do not advance the scheduled checkpoint.

A checkpoint advances only after normalized items have been safely written and
all configured targets for that source succeeded.

## Failure behavior

- transient HTTP failures use bounded retries;
- one category/edition failure is recorded without discarding successful target
  results in memory;
- any failed target prevents that source checkpoint from advancing;
- source page/result ceilings fail explicitly rather than silently truncating.

## GitHub Actions

- arXiv: `collect-arxiv.yml` at `01:37`, `07:37`, `13:37`, and `19:37`
  `Asia/Tokyo`;
- OpenReview: `collect-openreview.yml` six minutes later at `01:43`, `07:43`,
  `13:43`, and `19:43`;
- both share the repository-write concurrency group;
- only `data/items` and the source-specific state file are staged;
- `.chatgpt-workspace-manifest.json` is explicitly checked and never staged.

## Acceptance criteria

- [x] relevant arXiv entries normalize to the common paper schema;
- [x] arXiv cross-list duplicates collapse by base ID;
- [x] OpenReview notes normalize to the common paper schema;
- [x] configured venue editions map to canonical venue IDs;
- [x] current OpenReview status is normalized;
- [x] source checkpoints are independent and bounded;
- [x] fixture tests cover parsing, relevance, bootstrap, incremental collection,
  and stale-checkpoint behavior;
- [x] scheduled source workflows are present.
