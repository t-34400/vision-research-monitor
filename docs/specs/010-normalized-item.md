# Normalized Item

**Status:** Active  
**Related tasks:** `FND-007`  
**Related decisions:** `D-002`, `D-006`, `D-007`, `D-125`, `D-136`, `D-138`

## Purpose

Define the common record emitted by all collectors.

## Required conceptual fields

```text
id
source
source_id
kind
title
url
published_at
discovered_at
topics
metadata
```

## Recommended full shape

```yaml
id: string
source: string
source_id: string
kind: repository | release | tag | commit | paper | model | project | article | event

title: string
url: string
summary: string | null

authors: []
organization: string | null
venue: string | null

published_at: datetime | null
updated_at: datetime | null
discovered_at: datetime

topics: []
matched_terms: []

priority:
  source: number | null

scores:
  relevance: number | null
  freshness: number | null
  novelty: number | null
  popularity: number | null

related_items: []

metadata: {}
```

## Identity

`id` is the system identifier. `source_id` preserves the stable identifier from
the upstream source when available.

A normalized record must not rely on title text alone as its source identity.

## Time

All persisted timestamps are UTC. Source timestamps should be preserved without
inventing precision the source did not provide.

`discovered_at` records when this system first observed the item.

## Topics

Topic classification is multi-label.

An empty `topics` list is valid for a collected candidate that has not yet been
classified.

## Related items

`related_items` contains direct accepted links to other normalized item IDs.
Canonical append-only JSONL does not need to be rewritten when new links are
discovered: Phase 4 persists a derived relationship sidecar and materializes
`related_items` at read time.

Transitive membership in the same derived entity does not imply direct matching
evidence between every pair.

## Scores

Scores remain separate so ranking behavior is explainable and can be reweighted
without recollecting source data.

## Classification evidence

When classification evidence is available, collectors store it under
`metadata.classification`. The evidence may include the lexical score, semantic
model identifier, semantic similarity and per-topic scores, and optional LLM
model/reason.

`topics` and `scores.relevance` remain the normalized outputs consumed by
downstream ranking. Classifier-specific evidence stays in metadata so model or
provider changes do not alter the common item schema.

## Metadata

Source-specific fields that do not belong in the common schema may be retained
under `metadata`. Core behavior must not depend on opaque metadata when a stable
common field should exist instead.

## Evolution

Schema changes must update this specification before or together with the
implementation. Persisted data migration policy is an open decision until the
storage format is finalized.
