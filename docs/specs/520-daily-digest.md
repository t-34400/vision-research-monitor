# Daily Digest

**Status:** Active  
**Related tasks:** `RPT-007` through `RPT-010`  
**Related decisions:** `D-102`, `D-130`, `D-132`, `D-133`, `D-142`

## Purpose

Generate a deterministic Markdown digest and ranking sidecar from persisted
normalized items.

## Inputs

The digest builder reads:

- canonical normalized `data/items/**/*.jsonl`;
- taxonomy and venue configuration;
- linking configuration and regenerated entity links;
- `config/reporting.yaml`.

It does not call remote APIs.

## Reporting window

A digest date represents the **end date** of a 24-hour reporting window.

With the initial `Asia/Tokyo` timezone and `08:00` boundary:

```text
reports/daily/2026-08-08.md
  covers 2026-08-07 08:00 JST <= discovered_at < 2026-08-08 08:00 JST
```

The scheduled builder runs at 08:11 JST, after the 07:37 arXiv and 07:43
OpenReview runs. Manual `--date YYYY-MM-DD` builds the same deterministic window.

## Derived outputs

```text
data/entities/links.json
  current regenerated entity-link graph

data/ranking/YYYY-MM-DD.json
  report window, included item IDs, independent ranking signals, total score,
  watched override flag, and change label

reports/daily/YYYY-MM-DD.md
  human-readable digest
```

These outputs are derived and may be regenerated from canonical items and
configuration.

## Change labels

- `NEW`: paper/repository discovery or explicit creation/discovery action;
- `RELEASED`: GitHub release records;
- `ACCEPTED`: accepted OpenReview paper discovery or submitted-to-accepted
  status transition event;
- `UPDATED`: other included update/event records.

## OpenReview status transitions

The OpenReview collector keeps the last observed status per relevant note.
After bootstrap, it scans notes in descending true-modification order and stops
once a page is older than the overlapping checkpoint window. A changed status
emits a separate append-only event whose identity includes the note ID, previous
status, new status, and source modification timestamp.

This preserves the original first-seen paper record while allowing later
acceptance, rejection, or withdrawal changes to enter the digest.

## Paper deduplication

Before rendering, paper records in the same Phase 4 entity are represented once.
Non-paper events remain separate because a release, acceptance transition, or
repository update is itself reportable information.

The representative is selected deterministically by ranking order.

## Sections

The initial Markdown sections are:

1. Priority Watch
2. Accepted Papers
3. New Papers
4. New Repositories
5. Models & Demos
6. Research Announcements
7. Project Updates
8. Other

High-priority watched items appear in `Priority Watch` before normal section
classification and are not limited by normal ranking thresholds.

Hugging Face model records and reportable project/demo records use `Models &
Demos`. Official research-blog articles use `Research Announcements`. CVF project
sidecars marked `reportable: false` do not render separately; the paper entry
shows the first explicit Project and Code links when present.

Other sections use configurable per-section limits. Omitted counts are rendered
explicitly rather than silently disappearing.

## Failure behavior

The builder writes each derived file atomically. A failed build does not modify
collector checkpoints. The GitHub Actions workflow stages only
`data/entities`, `data/ranking`, and `reports/daily`, and separately verifies
that `.chatgpt-workspace-manifest.json` was not modified.

## Acceptance criteria

- [x] ranking signals remain separately inspectable;
- [x] high-priority watch items bypass the threshold;
- [x] positive star deltas influence popularity without using absolute stars;
- [x] OpenReview status changes produce append-only transition events;
- [x] `NEW`, `UPDATED`, `RELEASED`, and `ACCEPTED` are deterministic;
- [x] linked paper duplicates render once;
- [x] Markdown and ranking sidecars are reproducible for a fixed input set;
- [x] scheduled and manual digest builds use the same CLI path.
