# Roadmap

The roadmap follows one principle: **first collect reliably, then discover
broadly, then reduce noise intelligently**.

Statuses:

- `planned`: not started
- `active`: currently being implemented
- `complete`: phase exit criteria are satisfied
- `deferred`: intentionally postponed

## Phase 0 — Foundation

**Status:** complete

### Goal

Create the project contracts before implementing collectors.

### Deliverables

- project-wide rules;
- roadmap and task tracking;
- specification structure and templates;
- decision list;
- initial taxonomy shape;
- watchlist shape;
- normalized item schema;
- collector interface contract.

### Exit criteria

- future implementation work can reference stable documents instead of relying
  on chat history;
- open design questions are explicitly listed rather than hidden in code.

---

## Phase 1 — GitHub Watch

**Status:** complete

### Goal

Reliably detect changes in known high-value GitHub organizations, users, and
repositories.

### Scope

- organization/user repository enumeration;
- new repository detection;
- repository metadata changes;
- releases and tags;
- default-branch activity;
- explicit state/checkpoint handling.

### Exit criteria

A new repository or release from a configured high-priority watch target is
detected and normalized without relying on GitHub search.

---

## Phase 2 — GitHub Discovery

**Status:** complete

### Goal

Discover relevant repositories outside the watchlist.

### Scope

- topic query families;
- `created:` discovery windows;
- `pushed:` activity windows;
- venue/year repository searches;
- lexical candidate filtering;
- basic relevance scoring.

### Exit criteria

The system regularly finds relevant repositories that were not in the initial
watchlist while keeping the candidate volume operationally manageable.

---

## Phase 3 — Academic Discovery

**Status:** complete

### Goal

Collect relevant research before or independently of GitHub repository release.

### Scope

- arXiv collection;
- OpenReview collection;
- conference/venue metadata;
- title + abstract topic matching;
- source-specific checkpoints.

### Exit criteria

Relevant papers are normalized into the same item model as GitHub events.

---

## Phase 4 — Deduplication and Entity Linking

**Status:** complete

### Goal

Connect paper, repository, project page, and venue records that refer to the
same research work.

### Scope

- exact identifier matching;
- canonical URL normalization;
- normalized title comparison;
- author/repository evidence;
- `related_items` links;
- conservative merge policy.

### Exit criteria

Common duplicates are linked automatically without requiring destructive fuzzy
merges.

---

## Phase 5 — Ranking and Daily Digest

**Status:** active

### Goal

Turn collected items into a readable daily research digest.

### Scope

- priority;
- relevance;
- freshness;
- novelty;
- popularity delta;
- watched-source override;
- Markdown daily report;
- `NEW`, `UPDATED`, `RELEASED`, and `ACCEPTED` change labels.

### Exit criteria

A daily report can be generated deterministically from persisted normalized data.

---

## Phase 6 — Semantic Classification

**Status:** planned

### Goal

Improve recall and precision for research that does not use obvious keywords.

### Scope

- embeddings or semantic similarity;
- optional LLM classification after candidate reduction;
- multi-label topic assignment;
- reason/evidence capture;
- evaluation against a labeled sample.

### Exit criteria

Semantic classification measurably improves discovery quality over lexical
matching without becoming a collection dependency.

---

## Phase 7 — Source Expansion

**Status:** planned

### Goal

Add high-value sources without changing the core pipeline.

### Candidate sources

- CVF Open Access;
- Hugging Face;
- project pages;
- official research blogs;
- selected researcher pages or feeds.

### Exit criteria

At least one new source can be added through the collector contract with no core
pipeline redesign.

---

## Phase 8 — Long-Term Analysis

**Status:** planned

### Goal

Move from daily monitoring to trend analysis.

### Scope

- topic frequency over time;
- momentum signals;
- repository/paper growth rates;
- recurring entities;
- searchable archive or dashboard.

### Exit criteria

The system can answer both “what changed today?” and “what is accelerating over
the last N days?” from stored data.
