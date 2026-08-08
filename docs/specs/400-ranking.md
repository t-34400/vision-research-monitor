# Ranking

**Status:** Active  
**Related tasks:** `RPT-001` through `RPT-006`  
**Related decisions:** `D-005`, `D-006`, `D-129`, `D-130`, `D-131`

## Purpose

Rank normalized research items without hiding the evidence behind one opaque
score. Ranking is a presentation-stage operation and never changes collection
eligibility or canonical item identity.

## Configuration

Ranking configuration lives in `config/reporting.yaml` and is validated by
`config/schemas/reporting.schema.json`.

## Signals

Each candidate receives five independent values in the closed range `[0, 1]`:

- `priority`: explicit watch priority, source default, or venue priority;
- `relevance`: collector relevance score, with a configured fallback for items
  that already have taxonomy topics;
- `freshness`: exponential decay from the item's effective event time;
- `novelty`: configured by item kind and more specific source action;
- `popularity`: log-scaled positive GitHub star delta when available.

The derived ranking sidecar stores every signal as well as the weighted total.
The total is recomputable from configuration and is not canonical source data.

## Initial weights

```text
priority    0.30
relevance   0.30
freshness   0.15
novelty     0.20
popularity  0.05
```

The initial inclusion threshold is `0.35`.

## Priority

Explicit item source priority wins when it is stronger than the default source
or venue priority. Initial source defaults are deliberately small so an item is
not considered important merely because of its API source.

Core venues contribute `0.70`; secondary venues contribute `0.40`.

## Watched-source override

An item with explicit `priority.source >= 1.0` bypasses the normal total-score
threshold. The total and independent signals are still recorded so the item
remains explainable.

## Relevance

Use `scores.relevance` when the collector provides it. Otherwise an item with at
least one taxonomy topic receives the configured deterministic fallback (`0.55`
initially); unclassified items receive zero.

Semantic relevance remains a Phase 6 enhancement.

## Freshness

The initial half-life is 72 hours. Paper freshness prefers `published_at`, then
`discovered_at`. Repository freshness prefers `updated_at`, then `published_at`,
then `discovered_at`, so a previously old repository found through an active
`pushed` search is not treated as stale solely because of its creation date.
Update-like records prefer `published_at`, then `updated_at`, then
`discovered_at`.

Future timestamps are clamped to age zero rather than increasing freshness above
one.

## Novelty

A source action can override the generic item-kind value. New repositories,
releases, first discoveries, and creation events receive the strongest novelty;
routine metadata and branch-head changes receive lower values.

## Popularity

Popularity is based on **positive star growth observed between GitHub watch
snapshots**, not absolute star count. The signal is logarithmic and saturates at
the configured reference delta (`100` initially).

A star-count change by itself does not create a news item in Phase 5. The delta
is supporting evidence attached to another actionable repository event.
Discovery items start with `stars_delta = 0` because no prior observation exists.

## Determinism

For a fixed normalized item set, reporting configuration, venue registry, and
report window end, ranking output must be deterministic.
