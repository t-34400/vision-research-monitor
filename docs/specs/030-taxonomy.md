# Research Topic Taxonomy

**Status:** Active  
**Related tasks:** `FND-009`, `FND-010`  
**Related decisions:** `D-003`, `D-109`

## Purpose

Define the canonical topic identifiers used for classification, filtering,
ranking, reporting, and future discovery query generation.

## Files

- configuration: `config/taxonomy.yaml`
- schema: `config/schemas/taxonomy.schema.json`

## Model

The taxonomy has two levels:

1. `groups` organize related research areas for navigation and reporting;
2. `topics` are stable multi-label classification identifiers.

Group identifiers are not valid topic assignments. Downstream data must store
`topics[].id` values rather than group IDs or display labels.

## Topic fields

Each topic contains:

- `id`: stable machine-readable identifier;
- `label`: human-readable display name;
- `group`: owning group ID;
- `aliases`: lexical forms used for deterministic matching;
- optional `description`;
- optional `enabled` flag.

## Identifier stability

Topic IDs are persistent data identifiers. Renaming a display label or changing
aliases must not change the ID without an explicit migration decision.

## Matching semantics

Aliases are candidate matching terms, not a guarantee of relevance. Generic
aliases may produce false positives and must be evaluated with surrounding
metadata in later classification stages.

Discovery-specific GitHub queries belong to the Phase 2 discovery configuration,
not this taxonomy. Keeping the two separate allows search strategies to evolve
without changing stored topic identities.

## Multi-label behavior

An item may have zero, one, or many topics. Closely related topics such as
`pose_free_3d_reconstruction` and `unposed_3d_reconstruction` remain separate so
trends can be measured independently while allowing an item to receive both.

## Acceptance criteria

- every topic belongs to an existing group;
- group IDs and topic IDs are unique;
- aliases within each topic are unique;
- all agreed research themes have a corresponding topic or intentionally
  separated subtopics;
- configuration validates against the JSON Schema.
