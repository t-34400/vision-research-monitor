# Semantic Classification

**Status:** Active  
**Related tasks:** `SEM-001` through `SEM-006`  
**Related decisions:** `D-134`, `D-135`, `D-136`, `D-137`

## Purpose

Improve topic recall for relevant research that does not contain the exact
configured taxonomy aliases while preserving deterministic, explainable
collection behavior.

Semantic classification is an enhancement to candidate filtering. It must not
become a hard external-service dependency for GitHub or academic collection.

## Configuration

`config/semantic.yaml` is validated by
`config/schemas/semantic.schema.json`.

The configuration owns:

- the local semantic-profile model identifier;
- word and character n-gram ranges and feature weights;
- topic-selection and acceptance thresholds;
- multi-label enrichment behavior;
- optional ambiguity ranges for an LLM classifier;
- one curated semantic profile for every taxonomy topic;
- optional topic-specific anchor constraints used to suppress ambiguous general
  terms.

Every taxonomy topic must have exactly one semantic profile. Unknown and missing
topic IDs are configuration errors.

## Local semantic baseline

The default model is `topic-profile-tfidf-v1`.

For each taxonomy topic, the model builds a profile document from:

- the canonical topic label;
- configured taxonomy aliases;
- curated semantic hints that describe the concept without requiring its
  canonical name.

The model extracts word and character n-gram features, applies TF-IDF weights
computed over the topic profiles, L2-normalizes the profile and candidate
vectors, and uses cosine similarity for topic scoring.

The implementation is local and deterministic. It has no model download,
network request, or external runtime dependency.

## Candidate reduction

Semantic classification is never the first discovery step.

Candidate generation remains source-specific:

- GitHub candidates must first be surfaced by configured repository search or
  venue/year discovery;
- arXiv candidates must first be inside configured academic categories and the
  bounded collection window;
- OpenReview candidates must first belong to a configured conference edition.

The existing lexical classifier runs first.

When lexical relevance is below the source threshold, the semantic-profile model
may recover the candidate. When lexical relevance already passes, semantic
scoring may add additional relevant taxonomy labels, but it does not replace the
accepted lexical relevance score.

## Topic selection

Semantic classification is multi-label.

A topic is eligible when its profile similarity:

1. exceeds the configured absolute topic threshold; and
2. remains within the configured ratio of the strongest topic score.

The maximum number of semantic topics is bounded.

Some broad topic names use additional anchor constraints. For example,
Vision-Language Models require both visual and language evidence, while
Text-to-3D requires language evidence and 3D evidence. These constraints prevent
common words such as `model`, `generation`, or `text` from becoming standalone
semantic evidence.

## Optional LLM contract

The local semantic model is the default final classifier.

An optional `LLMTopicClassifier` contract accepts only:

- the candidate title and text;
- the bounded list of topic candidates produced by semantic scoring.

The LLM is eligible only when:

- lexical relevance was insufficient;
- semantic scoring produced topic candidates; and
- the best semantic score is inside the configured ambiguity range.

The core project does not select a hosted provider or require credentials in
Phase 6. A provider implementation can be added later without changing collector
contracts.

The LLM may return only topics from the semantic shortlist; out-of-shortlist
labels are ignored. If an optional LLM provider raises an error or is disabled,
the deterministic local semantic result remains sufficient for collection and
the provider error type is retained as classification evidence.

## Evidence and versioning

Newly classified normalized items store classification evidence under:

```text
metadata.classification
```

Evidence includes, as applicable:

- classification method;
- lexical score;
- semantic model identifier;
- semantic similarity;
- selected per-topic semantic scores;
- optional LLM model identifier;
- optional LLM reason.

The final relevance value remains in `scores.relevance`, and final topic labels
remain in `topics`.

This keeps ranking independent from classifier implementation details while
retaining enough evidence to reproduce or audit decisions.

## Evaluation

`evaluation/semantic_cases.yaml` is the small manually reviewed regression set.
It intentionally contains:

- direct lexical matches;
- paraphrases that the alias matcher misses;
- multi-label examples;
- unrelated negative examples.

`python -m vision_research_monitor.cli.evaluate_semantic` compares the semantic
pipeline with the Phase 3 lexical baseline using micro precision, recall, F1,
and exact-match rate.

The committed baseline is documented in
`docs/evaluations/semantic-baseline.md`.

The regression set is not a claim of production-level generalization. Future
real-world false positives and false negatives should be added to the reviewed
set before tuning thresholds or profiles.

## Failure behavior

- invalid or incomplete semantic configuration fails at startup;
- disabling semantic classification restores lexical-only behavior;
- collector code can operate without an injected semantic classifier;
- optional LLM classification is never required for successful collection;
- deterministic profile scoring does not alter source checkpoints or source
  identities.

## Acceptance criteria

- [x] every taxonomy topic has a validated semantic profile;
- [x] paraphrases can be recovered after source-level candidate reduction;
- [x] accepted lexical candidates can receive conservative multi-label semantic enrichment;
- [x] semantic decisions record model/version and score evidence;
- [x] the optional LLM contract receives only reduced semantic topic candidates;
- [x] collection continues without an LLM provider;
- [x] the reviewed evaluation set measures lexical and semantic precision/recall;
- [x] the semantic baseline improves F1 over the lexical baseline on the reviewed regression set.
