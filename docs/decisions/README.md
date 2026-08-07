# Decisions

`DECISIONS.md` is the lightweight architectural/product decision log.

Use it for choices that affect multiple modules, future extensibility, data
compatibility, or operational behavior.

## Status values

- `Accepted` — current baseline.
- `Proposed` — candidate decision requiring explicit resolution.
- `Superseded` — replaced by a newer decision.
- `Rejected` — considered and intentionally not chosen.

## Rule

Do not create an ADR file for every small implementation detail. Keep the list
lightweight until a decision requires substantial rationale. If an entry grows
too large, move its detailed rationale into a dedicated ADR and keep a summary
and link in `DECISIONS.md`.
