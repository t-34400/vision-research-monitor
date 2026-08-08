# Entity Linking and Deduplication

**Status:** Active  
**Related tasks:** `LNK-001` through `LNK-006`  
**Related decisions:** `D-007`, `D-125`, `D-126`, `D-127`, `D-128`

## Purpose

Connect normalized records that refer to the same research work while avoiding
irreversible fuzzy merges.

Phase 4 produces a derived relationship graph. It does not rewrite canonical
append-only collection history.

## Inputs and output

The linker reads normalized records from `data/items/**/*.jsonl` and writes:

```text
data/entities/links.json
```

The sidecar contains:

- direct accepted links and their evidence;
- connected entity components derived from those links;
- a direct `related_items` mapping for each linked item.

`related_items` can be materialized into `NormalizedItem` instances at read time.
The original JSONL records remain unchanged.

## Configuration

`config/linking.yaml` is validated by
`config/schemas/linking.schema.json`.

The configuration owns:

- URL tracking-parameter removal;
- metadata fields eligible for stable external-identifier extraction;
- exact/fuzzy title thresholds;
- author-overlap thresholds;
- conservative repository-name matching rules;
- generic repository names that must never be treated as distinctive evidence.

## URL normalization

HTTP/HTTPS URLs are normalized before identity comparison:

- host names are case-folded and leading `www.` is removed;
- output uses HTTPS identity form;
- fragments are removed;
- trailing slashes are normalized;
- configured tracking query parameters are removed;
- remaining query parameters are sorted;
- arXiv `/abs` and `/pdf` version URLs normalize to the base arXiv abstract URL;
- OpenReview `/forum` and `/pdf` URLs normalize to the forum URL by note ID.

URL normalization is for identity comparison only. The original source URL stays
on the normalized item.

## Exact identifiers

The linker extracts strong identifiers from source identity, item URLs, and an
allowlist of metadata fields.

Supported identifiers include:

- base arXiv IDs;
- OpenReview note IDs;
- GitHub repository numeric IDs;
- GitHub `owner/repository` URLs;
- DOI values;
- canonical external URLs.

GitHub release, tag, commit, and repository events use the repository ID prefix
from their `source_id`, so they link deterministically to the corresponding
repository record when present.

Shared exact identifiers create direct links with confidence `1.0`.

## Paper title matching

Title matching only applies to paper records.

### Exact normalized title

Punctuation, case, accents, and repeated whitespace are normalized. A normalized
title match is accepted only when:

- the normalized title is at least the configured minimum length; and
- normalized author overlap reaches the configured threshold.

A title match by itself never links two papers.

### Fuzzy normalized title

Fuzzy matching uses deterministic sequence similarity after title
normalization. Candidate pairs are blocked through shared title tokens to avoid
an unbounded all-pairs comparison. Extremely common token blocks above the
configured maximum are skipped rather than expanding quadratically.

A fuzzy match is accepted only when both configured thresholds are met:

- title similarity;
- author overlap.

This intentionally favors false negatives over false merges.

## Author evidence

Authors are normalized using Unicode decomposition, case folding, punctuation
removal, surname, and first initial. The overlap score is the matched-author
count divided by the smaller author-list size.

Author evidence supports a title match. Author overlap alone never creates a
link.

## Repository-name evidence

Repository-name matching is a fallback for repository-to-paper links when no
strong external identifier already linked the pair.

A repository name must:

- meet the configured minimum normalized length;
- not be in the generic-name denylist;
- appear as a complete normalized phrase/token in the paper title; and
- share at least one taxonomy topic when topic overlap is required.

Repository-name and topic evidence create a direct related link but do not
rewrite either record.

## Entity components

Accepted direct links form an undirected graph. Connected components containing
at least two records receive deterministic entity IDs derived from their sorted
item IDs.

Direct `related_items` only lists immediate accepted neighbors. It does not
implicitly claim that every member of a transitive component had direct matching
evidence with every other member.

## Failure and replay behavior

The linker is deterministic for the same item set and configuration except for
the output `generated_at` timestamp. It performs no network requests.

`data/entities/links.json` is fully derived and can be safely regenerated from
canonical items. A failed write uses atomic replacement and leaves the previous
complete sidecar intact.

## Acceptance criteria

- [x] URLs and supported source identifiers are normalized deterministically.
- [x] Exact identifiers link GitHub repository activity and cross-source records.
- [x] Normalized-title matching requires supporting author evidence.
- [x] Repository-name evidence requires a distinctive name and configured topic support.
- [x] Direct relationships can be materialized as `related_items` without mutating JSONL history.
- [x] Regression tests reject identical-title papers with unrelated authors and generic repository-name collisions.
