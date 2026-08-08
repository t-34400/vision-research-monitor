# Semantic Classification Baseline

Evaluation set: `evaluation/semantic_cases.yaml`  
Cases: 30  
Semantic model: `topic-profile-tfidf-v1`

## Results

| Pipeline | Precision | Recall | F1 | Exact match |
|---|---:|---:|---:|---:|
| Phase 3 lexical baseline | 1.0000 | 0.2258 | 0.3684 | 0.4000 |
| Phase 6 semantic pipeline | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

F1 delta: **+0.6316**.

## Interpretation

The main measured gain is recall on intentionally paraphrased cases where exact
taxonomy aliases are absent. The evaluation also contains unrelated negatives
and multi-label examples.

This is a compact regression set curated alongside the first semantic profiles,
so the result should not be interpreted as an unbiased estimate of production
accuracy. Its purpose is to prevent regressions and to make future profile or
threshold changes measurable. Real collection mistakes should be added to this
set before retuning the classifier.
