# Collector Contract

**Status:** Active  
**Related tasks:** `FND-008`  
**Related decisions:** `D-001`, `D-003`, `D-005`

## Purpose

Define behavior shared by GitHub, arXiv, OpenReview, and future collectors.

## Inputs

A collector receives:

- validated source configuration;
- a bounded collection window or explicit checkpoint;
- source credentials when required;
- previously persisted source state.

## Outputs

A collector returns:

1. zero or more source records suitable for normalization;
2. updated source state/checkpoint;
3. structured diagnostics for skipped or failed records.

## Requirements

### Idempotency

Re-running the same window/checkpoint must not create duplicate logical records.

### Bounded work

Discovery collectors must use explicit time windows or pagination/checkpoints.
They must not unintentionally perform an unbounded historical crawl.

### Traceability

Every emitted record must preserve enough source information to retrieve or
identify the upstream object again.

### Failure isolation

A failure for one source, page, or record must not erase successful results from
other independent sources.

### State commit

A checkpoint must advance only after the corresponding successfully processed
data is safely persisted.

### Retry behavior

Retry transient network/server failures with bounded exponential backoff.
Authentication, schema, and clearly permanent request errors should fail fast
with actionable diagnostics.

### Rate limits

Collectors must expose or log remaining limits when the source provides them and
avoid aggressive polling when limits are low.

### Conditional requests

Use ETag or last-modified semantics when supported and when they reduce quota or
bandwidth.

## Collector/non-collector responsibilities

Collectors do:

- source API calls;
- pagination;
- source-specific parsing;
- source checkpoint management.

Collectors do not:

- calculate final digest ordering;
- merge unrelated source entities;
- call semantic/LLM classification by default;
- decide report presentation.

## Test contract

Each collector should have fixture-based tests for:

- empty result;
- one valid result;
- pagination;
- malformed optional data;
- retryable failure;
- checkpoint behavior;
- repeat-run idempotency.
