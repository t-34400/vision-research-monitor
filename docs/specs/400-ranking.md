# Ranking

**Status:** Active  
**Related tasks:** `RPT-001` through `RPT-006`  
**Related decisions:** `D-005`, `D-006`, `D-129`, `D-130`, `D-131`, `D-142`, `D-158`

## Purpose

Rank normalized research items without hiding the evidence behind one opaque
score. Ranking is a presentation-stage operation and never changes collection
eligibility or canonical item identity.

## Configuration

Ranking configuration lives in `config/reporting.yaml` and is validated by
`config/schemas/reporting.schema.json`.

## Signals

Each candidate receives six independent values in the closed range `[0, 1]`:

- `priority`: explicit watch priority, source default, or venue priority;
- `relevance`: collector topical relevance score, with a configured fallback
  for items that already have taxonomy topics;
- `research`: repository research-value evidence when supplied by GitHub
  Discovery, otherwise an unrestrictive fallback for sources not using this gate;
- `freshness`: exponential decay from the item's effective event time;
- `novelty`: configured by item kind and more specific source action;
- `popularity`: log-scaled positive GitHub star delta when available.

The derived ranking sidecar stores every signal as well as the weighted total.
The `research` signal is currently an inclusion gate for GitHub Discovery
repositories rather than an additional weighted term, so introducing it does not
silently retune cross-source ordering. The total remains recomputable from
configuration and is not canonical source data.

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

Core venues contribute `0.70`; secondary venues contribute `0.40`. Initial
expanded-source defaults are deliberately modest: CVF `0.30`, Hugging Face
`0.15`, and official research blogs `0.20`. A configured feed may provide a
stronger explicit source priority.

## Watched-source override

An item with explicit `priority.source >= 1.0` bypasses the normal total-score
threshold. The total and independent signals are still recorded so the item
remains explainable.

## Relevance

Use `scores.relevance` when the collector provides it. Otherwise an item with at
least one taxonomy topic receives the configured deterministic fallback (`0.55`
initially); unclassified items receive zero.

Semantic relevance remains a Phase 6 enhancement.

## Research value

GitHub Discovery writes `scores.research_relevance` independently from topical
relevance. A discovered GitHub repository must meet
`minimum_github_repository_research_score` before the normal total-score threshold
can include it in the digest. This gate suppresses generic tutorials, demo apps,
and curated/awesome lists while preserving them in collected data for later
inspection and trend experiments.

Legacy GitHub Discovery records that predate `research_relevance` fail closed at
this gate instead of receiving an optimistic fallback. Explicit watch priority
still overrides the gate, so known watched repositories are never hidden merely
because discovery-oriented research evidence is missing.

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
routine metadata and branch-head changes receive lower values. Phase 7 adds
model, project, and article kinds plus `published` and `updated` actions.

Items with `metadata.reportable = false` are excluded before threshold handling.
This is used for relationship sidecars such as CVF-discovered project pages that
should enrich a parent paper without appearing as a duplicate digest entry.

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
