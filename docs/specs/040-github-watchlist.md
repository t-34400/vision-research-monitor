# GitHub Watchlist

**Status:** Active  
**Related tasks:** `FND-011`, `FND-012`  
**Related decisions:** `D-003`, `D-005`, `D-104`, `D-109`, `D-162`

## Purpose

Define known GitHub accounts and repositories whose changes are collected
without relying on broad GitHub search.

## Files

- configuration: `config/github_watchlist.yaml`
- schema: `config/schemas/watchlist.schema.json`

## Account model

`account_discovery` configures bounded direct scans of known accounts:

- `overlap_minutes`: safety overlap before the previous account checkpoint;
- `max_pages_per_run`: hard pagination bound for repositories sorted by newest creation time.

Each watched account contains:

- `login`: GitHub login;
- `type`: `organization` or `user`;
- `priority`: `high` or `normal`;
- `topic_filter_required`: whether normal report inclusion requires topic
  relevance;
- optional `notes` and `enabled`.

`high` identifies a source whose relevant source changes must not disappear only
because a ranking score is low. It does not mean every commit from that account
must be presented as news.

`topic_filter_required` remains source metadata for broad organizations that
publish substantial work outside this project's research scope. Account scans
only emit newly created repositories; update-level monitoring is handled by
explicit and auto-promoted repository targets.

## Repository model

Repositories may be watched independently of their owning account. Each entry
contains:

- `repo` in `owner/name` form;
- `priority`;
- optional known topic IDs;
- optional `notes` and `enabled`.

Direct repository entries take precedence over account defaults when later watch
logic calculates inclusion policy.

## Initial scope

The initial account set covers the explicitly requested large research
organizations plus nerfstudio-related projects. The list is intentionally small
and configuration-driven; Phase 1 must make additions possible without code
changes.

## Acceptance criteria

- account logins are unique;
- repository names are unique;
- every configured repository topic exists in `config/taxonomy.yaml`;
- configuration validates against the JSON Schema.
