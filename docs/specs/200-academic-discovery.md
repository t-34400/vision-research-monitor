# Academic Discovery

**Status:** Active  
**Related tasks:** `ACA-001` through `ACA-008`  
**Related decisions:** `D-120`, `D-121`, `D-122`, `D-123`, `D-124`, `D-134`, `D-135`

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

Topic classification is multi-label. Phase 3 lexical matching remains the first
filter. From Phase 6 onward, candidates below the lexical threshold can be
recovered by the deterministic semantic-profile classifier after source-level
candidate reduction. Lexically accepted papers may also receive semantic
multi-label enrichment.

The semantic classifier is local and optional from the collector contract's
perspective. A collector instantiated without it retains Phase 3 lexical-only
behavior, so semantic classification is not an external collection dependency.

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

After bootstrap, collection requests notes in descending `tmdate` order and
scans until the oldest true modification on a page is older than the overlapping
source window. The collector locally enforces the upper window boundary. A page
limit is a hard coverage failure rather than a silent truncation.

This modification-ordered scan is required because a note can be created before
the current collection window and later change publication/status metadata.

### Status normalization

OpenReview notes normalize to:

- `withdrawn` when the venue label indicates withdrawal;
- `rejected` when the venue label indicates rejection;
- `accepted` when `pdate` is present;
- `submitted` otherwise.

The current status is stored in item metadata and in the source-specific note
state. When an already observed relevant note changes status, the collector emits
a separate append-only `event` record with `action: status_changed`. This keeps
the original paper record immutable while supporting later Phase 5 change
labels.

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
- [x] fixture tests cover parsing, relevance, bootstrap, modification-ordered
  incremental collection, status transitions, and stale-checkpoint behavior;
- [x] scheduled source workflows are present.
