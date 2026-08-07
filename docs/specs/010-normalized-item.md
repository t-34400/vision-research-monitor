# Normalized Item

**Status:** Active  
**Related tasks:** `FND-007`  
**Related decisions:** `D-002`, `D-006`, `D-007`

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
kind: repository | release | tag | commit | paper | project | event

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

## Scores

Scores remain separate so ranking behavior is explainable and can be reweighted
without recollecting source data.

## Metadata

Source-specific fields that do not belong in the common schema may be retained
under `metadata`. Core behavior must not depend on opaque metadata when a stable
common field should exist instead.

## Evolution

Schema changes must update this specification before or together with the
implementation. Persisted data migration policy is an open decision until the
storage format is finalized.
