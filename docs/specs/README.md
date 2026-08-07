# Specifications

This directory contains the current intended behavior of the system.

Specifications answer **what the system should do**. Architectural choices and
their rationale belong in `../decisions/DECISIONS.md`.

## Files

- `000-system-overview.md` — system boundaries and pipeline stages.
- `010-normalized-item.md` — common item model shared by all sources.
- `020-collector-contract.md` — required behavior of source collectors.
- `_template.md` — template for future specifications.

## Naming

Use a stable numeric prefix so related specs remain ordered:

```text
000-099  system/core
100-199  GitHub
200-299  academic sources
300-399  linking/deduplication
400-499  classification/ranking
500-599  reporting/persistence
600-699  automation/operations
```

## Spec lifecycle

A spec may contain:

- `Status: Draft`
- `Status: Active`
- `Status: Deprecated`

Do not delete old behavior without recording the replacement when the change is
architecturally meaningful.

## Change rule

Implementation and specification changes should land together. If code and spec
disagree, the mismatch is a defect rather than an undocumented exception.
