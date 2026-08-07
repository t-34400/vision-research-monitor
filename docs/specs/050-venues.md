# Academic Venue Registry

**Status:** Active  
**Related tasks:** `FND-013`  
**Related decisions:** `D-105`, `D-109`

## Purpose

Define stable venue identifiers and source hints for academic discovery.

## Files

- configuration: `config/venues.yaml`
- schema: `config/schemas/venues.schema.json`

## Venue fields

Each venue contains:

- `id`: stable machine-readable identifier;
- `name`: canonical display name;
- `domains`: one or more of vision, machine learning, graphics, robotics, XR;
- `priority`: `core` or `secondary`;
- `aliases`: short names and common textual forms;
- `sources`: expected publication/index sources;
- optional `enabled`.

## Priority semantics

`core` venues are directly aligned with the monitoring scope and should receive
full discovery coverage when a collector for their source is available.

`secondary` venues are broader or adjacent. Their papers should normally require
topic relevance before appearing in the digest.

## Year handling

The registry represents conference series, not individual yearly editions.
Year-specific identifiers and URLs are source data discovered or configured by
the academic collector. This avoids editing the core venue registry every year.

## Workshops

Workshop discovery is in scope for Phase 3 but workshops are not enumerated as
permanent venue entries here. They should inherit the parent conference context
when possible and retain their own source identifiers.

## Acceptance criteria

- venue IDs are unique;
- aliases within each venue are unique;
- the initial registry covers core vision/3D, graphics, robotics, major ML, and
  XR venues needed by the current taxonomy;
- configuration validates against the JSON Schema.
