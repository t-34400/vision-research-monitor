# Source Expansion

**Status:** Active  
**Related tasks:** `SRC-001` through `SRC-005`  
**Related decisions:** `D-138` through `D-145`

## Purpose

Add high-value sources beyond GitHub, arXiv, and OpenReview without introducing
source-specific downstream pipelines.

Every accepted record continues through the common normalized-item,
classification, linking, ranking, persistence, and reporting contracts.

## Configuration

`config/sources.yaml` is validated by
`config/schemas/sources.schema.json`.

It owns:

- shared bounded-window defaults for time-indexed expanded sources;
- lexical matching weights;
- configured CVF proceedings editions;
- Hugging Face model-search queries and request/page limits;
- official RSS/Atom feed URLs and source priorities.

Cross-file CVF venue IDs are validated against `config/venues.yaml`.

## CVF Open Access

CVF Open Access does not expose the same incremental collection contract as
arXiv/OpenReview, so the collector treats each configured proceedings page as an
inventory.

For each edition the collector:

1. downloads every configured index page;
2. parses paper detail URLs and source IDs;
3. rejects an unexpectedly small index or an inventory that loses a previously
   observed paper ID before changing state;
4. uses the first successful run as a baseline inventory without emitting old
   proceedings as new research;
5. on later runs, fetches only newly observed paper detail pages;
6. classifies the paper title/abstract through the existing lexical + semantic
   pipeline;
7. emits relevant papers using `source=cvf`, `kind=paper`.

The minimum-index and monotonic-inventory guards intentionally turn a likely
upstream HTML-layout change or partial response into a failed target instead of
replacing a complete inventory with a truncated one.

### Project and code extraction

A CVF paper detail page may explicitly link to project pages, code repositories,
PDFs, supplements, BibTeX, and other external resources.

The collector stores explicit `project_urls`, `code_urls`, and `external_urls` on
the parent paper metadata. It may additionally emit a `kind=project` sidecar for
an explicit project URL. That sidecar:

- declares the parent paper ID in `related_items`;
- carries `metadata.reportable = false`;
- exists to preserve an explicit source relationship, not to create another
  digest headline.

GitHub/code URLs remain metadata links so the generic linker can connect them to
repository records when those records exist.

## Hugging Face

The initial Hugging Face scope is public **model repositories**. Spaces and
datasets are not collected in Phase 7.

For each configured query the collector calls the Hub model listing endpoint,
sorted by descending `lastModified`, and follows pagination until the bounded
window is crossed. The scheduled window uses:

- 72-hour initial lookback;
- 180-minute overlap;
- 168-hour maximum automatic catch-up.

If a query reaches its page safety limit before crossing the window, that query
fails and the source checkpoint does not advance.

Candidates are deduplicated by model repository ID across queries. A repository
revision is represented by `repo_id@lastModified` and an unchanged revision is
not re-emitted. Requests are paced at 0.75 seconds initially; HTTP 429 and
transient server failures use the shared bounded retry behavior.

Model ID, pipeline tag, Hub tags, and card metadata are classified first. When
lexical relevance is insufficient, a bounded number of model README cards may be
fetched for additional evidence. Semantic classification remains optional and
local by default.

`HF_TOKEN` is optional. Public endpoints can operate without it; a configured
token is used when available.

## Official research feeds

The initial feed set contains stable official RSS/Atom feeds for:

- Google Research;
- Microsoft Research;
- Apple Machine Learning Research.

The collector parses RSS 2.0 and Atom locally, applies the same bounded source
window as Hugging Face, and classifies title, summary/content, and categories.
Inline XML/HTML element boundaries are normalized so adjacent text nodes do not
collapse words in titles or summaries, including boundaries after sentence
punctuation such as `.</span>The` or `,</a>as`. Punctuation attachment is
preserved so the normalization does not introduce spaces before commas, periods,
or closing brackets. Relevant records normalize to `source=research_blog`,
`kind=article`.

A feed configuration can assign explicit source priority, but publication by a
large organization alone is not sufficient for topic relevance.

A failed feed is isolated from other feeds but prevents the shared research-blog
checkpoint from advancing, so the failed time range can be replayed.

## Selected researcher sources

Phase 7 does not add a generic crawler for individual researcher pages. Personal
sites have inconsistent publication/update semantics, stable feeds are uncommon,
and no curated researcher list has yet been specified.

A researcher source should be added only when it has a stable machine-readable
feed/API or an explicit high-value watch target. Such a source can reuse this
collector contract later without changing downstream stages.

## State and idempotency

Expanded sources keep independent state files:

```text
data/state/cvf.json
data/state/huggingface.json
data/state/research_blogs.json
```

CVF persists edition inventories. Hugging Face persists last-seen repository
revisions plus a source checkpoint. Research blogs persist a source checkpoint.

Normalized item IDs are deterministic. Replaying overlapping windows is safe
because the JSONL store deduplicates already persisted item IDs.

## Reporting

- CVF papers render with normal paper sections and show explicit Project/Code
  links when available;
- Hugging Face models render under `Models & Demos`;
- official feed articles render under `Research Announcements`;
- non-reportable relationship sidecars never bypass report exclusion, even if
  their ranking total would otherwise pass.

## Failure behavior

- source-level coverage failures prevent that source checkpoint from advancing;
- one configured target can fail without deleting items returned by successful
  targets;
- invalid configuration fails before network collection;
- collectors never modify `.chatgpt-workspace-manifest.json`;
- raw HTML/feed/model-card responses are not canonical persistence.

## Acceptance criteria

- [x] CVF inventory changes produce normalized relevant paper records.
- [x] CVF project/code links are preserved and can participate in entity linking.
- [x] Hugging Face model searches are bounded and revision-idempotent.
- [x] RSS 2.0 and Atom official feeds produce normalized relevant articles.
- [x] expanded-source records use the existing semantic-classification pipeline.
- [x] expanded-source records appear in deterministic digest sections.
- [x] individual researcher crawling remains explicitly deferred pending stable targets.
