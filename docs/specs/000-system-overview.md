# System Overview

**Status:** Active  
**Related tasks:** `FND-006`  
**Related decisions:** `D-001`, `D-002`, `D-003`, `D-004`

## Purpose

Define the boundaries and stage separation of the research-monitoring pipeline.

## Pipeline

```text
Known targets ───────> GitHub Watch ───────┐
                                           │
GitHub search ───────> GitHub Discover ────┼─> Normalize
                                           │      │
arXiv/OpenReview ────> Academic ───────────┘      v
                                              Persist
                                                 │
                                                 v
                                         Link / Deduplicate
                                                 │
                                                 v
                                         Classify / Rank
                                                 │
                                                 v
                                              Report
```

## Stage responsibilities

### Collect

Collectors retrieve source facts and source-specific metadata.

Collectors must not make irreversible cross-source merge decisions.

### Normalize

Source records become the common normalized item described in
`010-normalized-item.md`.

### Persist

Normalized items and source checkpoints are stored independently. Replaying a
collector window must be safe.

### Link / Deduplicate

Records referring to the same research work are connected using deterministic
identifiers first and fuzzy evidence only when necessary.

### Classify / Rank

Topic classification is multi-label. Ranking combines independent signals rather
than one hidden score.

### Report

Reports are derived outputs. The canonical data must not depend on a report
having been generated successfully.

## Source classes

### Watch

Known organizations, users, and repositories where missing an update is costly.

### Discover

Broad search intended to surface unknown repositories. Higher noise is acceptable
before candidate filtering.

### Academic

Paper/conference sources that may reveal work before code is published.

## Non-goals for early phases

- real-time streaming;
- fully autonomous semantic classification;
- perfect paper/repository entity resolution;
- dashboard/UI before the daily data pipeline is trustworthy.
