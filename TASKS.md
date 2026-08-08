# Task List

Task IDs are stable. Completed tasks should remain in this file for history.

## Phase 0 — Foundation

- [x] `FND-001` Define project-wide rules.
- [x] `FND-002` Create roadmap and phase exit criteria.
- [x] `FND-003` Create task-tracking conventions.
- [x] `FND-004` Create specification directory and template.
- [x] `FND-005` Create architectural/product decision list.
- [x] `FND-006` Draft system overview specification.
- [x] `FND-007` Draft normalized item schema specification.
- [x] `FND-008` Draft collector contract specification.
- [x] `FND-009` Define initial taxonomy configuration schema.
- [x] `FND-010` Populate initial taxonomy from the agreed research themes.
- [x] `FND-011` Define watchlist configuration schema.
- [x] `FND-012` Populate initial organization/user/repository watchlist.
- [x] `FND-013` Define venue configuration schema.
- [x] `FND-014` Resolve Phase 0 open decisions in the decision list.
- [x] `FND-015` Define repository data-retention strategy.
- [x] `FND-016` Define reporting timezone and schedule policy.

## Phase 1 — GitHub Watch

- [x] `GHW-001` Implement GitHub API client abstraction.
- [x] `GHW-002` Implement rate-limit and retry handling.
- [x] `GHW-003` Implement conditional request support.
- [x] `GHW-004` Implement organization/user repository enumeration.
- [x] `GHW-005` Detect newly created repositories for watch targets.
- [x] `GHW-006` Detect repository metadata changes.
- [x] `GHW-007` Collect releases and tags.
- [x] `GHW-008` Collect default-branch activity.
- [x] `GHW-009` Define persistent watch state/checkpoints.
- [x] `GHW-010` Normalize GitHub watch events to the common item model.
- [x] `GHW-011` Add fixture-based tests.
- [x] `GHW-012` Add `collect-github-watch.yml`.
- [x] `GHW-013` Verify idempotent reruns.

## Phase 2 — GitHub Discovery

- [x] `GHD-001` Define discovery query configuration schema.
- [x] `GHD-002` Add topic query families.
- [x] `GHD-003` Add repository `created:` discovery.
- [x] `GHD-004` Add repository `pushed:` discovery.
- [x] `GHD-005` Add venue/year README discovery.
- [x] `GHD-006` Add bounded collection windows and checkpoints.
- [x] `GHD-007` Add lexical candidate scoring.
- [x] `GHD-008` Normalize discovered repositories.
- [x] `GHD-009` Add fixture-based tests.
- [x] `GHD-010` Add `collect-github-discovery.yml`.

## Phase 3 — Academic Discovery

- [x] `ACA-001` Implement arXiv collector.
- [x] `ACA-002` Add arXiv checkpointing.
- [x] `ACA-003` Implement title + abstract lexical matching.
- [x] `ACA-004` Implement OpenReview collector.
- [x] `ACA-005` Add venue mapping and status normalization.
- [x] `ACA-006` Normalize academic records to the common item model.
- [x] `ACA-007` Add fixture-based tests.
- [x] `ACA-008` Add academic GitHub Actions workflows.

## Phase 4 — Deduplication and Entity Linking

- [x] `LNK-001` Normalize URLs and source identifiers.
- [x] `LNK-002` Implement exact identifier linking.
- [x] `LNK-003` Implement normalized-title matching.
- [x] `LNK-004` Add author/repository supporting evidence.
- [x] `LNK-005` Implement conservative `related_items`.
- [x] `LNK-006` Add false-merge regression tests.

## Phase 5 — Ranking and Reporting

- [x] `RPT-001` Define ranking signal schema.
- [x] `RPT-002` Implement source priority.
- [x] `RPT-003` Implement relevance score.
- [x] `RPT-004` Implement freshness and novelty signals.
- [x] `RPT-005` Implement popularity-delta signal.
- [x] `RPT-006` Implement watched-source inclusion override.
- [x] `RPT-007` Generate deterministic Markdown daily digest.
- [x] `RPT-008` Add change labels.
- [x] `RPT-009` Add `build-digest.yml`.
- [x] `RPT-010` Track OpenReview status transitions before emitting academic change labels.

## Phase 6 — Semantic Classification

- [x] `SEM-001` Build a small manually reviewed evaluation set.
- [x] `SEM-002` Add semantic similarity baseline.
- [x] `SEM-003` Measure precision/recall against lexical baseline.
- [x] `SEM-004` Design optional LLM classifier contract.
- [x] `SEM-005` Add semantic/LLM classification only after candidate reduction.
- [x] `SEM-006` Record classification evidence and model/version metadata.

## Phase 7 — Source Expansion

- [ ] `SRC-001` Evaluate CVF collector.
- [ ] `SRC-002` Evaluate Hugging Face collector.
- [ ] `SRC-003` Define project-page extraction strategy.
- [ ] `SRC-004` Add official research-blog sources.
- [ ] `SRC-005` Add selected researcher sources if signal quality justifies it.

## Phase 8 — Long-Term Analysis

- [ ] `TRD-001` Define time-series aggregation model.
- [ ] `TRD-002` Track per-topic item counts.
- [ ] `TRD-003` Track repository/paper momentum.
- [ ] `TRD-004` Add rolling-window trend detection.
- [ ] `TRD-005` Evaluate searchable archive/dashboard options.

## Task conventions

Each implementation PR/change should:

1. reference one or more task IDs;
2. update task status when work is completed;
3. update the affected spec when behavior changes;
4. update the decision list when an architectural choice is made or reversed.
