# Scheduling Policy

**Status:** Active  
**Related tasks:** `FND-016`  
**Related decisions:** `D-103`, `D-108`, `D-145`, `D-151`, `D-159`, `D-160`, `D-161`

## Purpose

Define the initial GitHub Actions cadence and time semantics.

## Timezones

- persisted timestamps: UTC;
- report/display timezone: `Asia/Tokyo`;
- GitHub Actions schedules: `timezone: "Asia/Tokyo"`, so cron expressions use local wall-clock time.

## Current cadence

| Workflow | Local schedule (Asia/Tokyo) | Cron |
| --- | --- | --- |
| GitHub Watch | 08:05 daily | `5 8 * * *` |
| arXiv | 08:10 daily | `10 8 * * *` |
| Hugging Face | 08:15 daily | `15 8 * * *` |
| CVF Open Access | 08:20 daily | `20 8 * * *` |
| Research Blogs | 08:25 daily | `25 8 * * *` |
| GitHub Discovery | 08:30 daily | `30 8 * * *` |
| Daily Digest + Long-Term Analysis | 08:45 daily | `45 8 * * *` |

The daily digest and long-term analysis keep the 08:00 local reporting boundary.
Collectors start just after the boundary and are staggered at five-minute intervals;
the shared queued writer group serializes them if a previous collector is still
running. The digest workflow is scheduled for 08:45 so it naturally follows the
morning collection batch. OpenReview remains available as a manual/local collector
but is intentionally not scheduled in GitHub Actions while unattended API access
requires challenge verification. A digest date is the end date of the preceding
24-hour reporting window.

## Action runtime policy

Scheduled and manually dispatched workflows:

- check out the repository default branch explicitly because canonical runtime data is stored there;
- install uv with `astral-sh/setup-uv`, pinned to the reviewed Action revision;
- install uv `0.12.3` and Python `3.13`, matching the locally validated toolchain;
- run `uv sync --locked --no-dev` before application commands;
- execute application commands with `uv run --locked --no-sync` so the lockfile cannot be silently changed and the already-synchronized environment is reused;
- serialize all canonical writers with the shared `research-monitor-writes` concurrency group and `queue: max`, so bursts of manual or scheduled runs wait instead of replacing pending runs;
- stage only the allowlisted data/state/report paths owned by that workflow, skipping absent empty-output paths while still committing collector state;
- rebase the resulting commit onto the current default branch immediately before push, handling unrelated repository changes without staging them.

OpenReview remains excluded from scheduled Actions per `D-156`.

## Scheduling rules

- avoid top-of-hour cron expressions;
- use workflow concurrency controls once canonical writes are implemented;
- a delayed scheduled run still processes from persisted checkpoints rather than
  assuming it executed at the nominal cron time;
- manual `workflow_dispatch` runs must use the same checkpoint semantics as
  scheduled runs;
- collection windows should overlap slightly when source APIs have uncertain
  indexing latency, with normalized identity handling duplicates safely.

## Change policy

Cadence is operational configuration. Changing times does not require a schema
migration, but changes must update this specification and `D-103` if the overall
strategy changes.
