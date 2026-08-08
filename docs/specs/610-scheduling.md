# Scheduling Policy

**Status:** Active  
**Related tasks:** `FND-016`  
**Related decisions:** `D-103`, `D-108`, `D-145`, `D-151`, `D-159`, `D-160`

## Purpose

Define the initial GitHub Actions cadence and time semantics.

## Timezones

- persisted timestamps: UTC;
- report/display timezone: `Asia/Tokyo`;
- GitHub Actions cron expressions: UTC, as required by the platform.

## Initial cadence

| Workflow | Local schedule (Asia/Tokyo) | UTC cron |
| --- | --- | --- |
| GitHub Watch | 00:17, 06:17, 12:17, 18:17 daily | `17 3,9,15,21 * * *` |
| arXiv | 01:37, 07:37, 13:37, 19:37 daily | `37 4,10,16,22 * * *` |
| Hugging Face | 02:29, 08:29, 14:29, 20:29 daily | `29 5,11,17,23 * * *` |
| CVF Open Access | 03:23 daily | `23 18 * * *` |
| Research Blogs | 03:31, 09:31, 15:31, 21:31 daily | `31 0,6,12,18 * * *` |
| GitHub Discovery | 04:47, 16:47 daily | `47 7,19 * * *` |
| Daily Digest + Long-Term Analysis | 08:11 daily | `11 23 * * *` |

The daily digest and long-term analysis share the 08:00 local reporting boundary
and run in one 08:11 workflow, after the 07:37 arXiv collection slot. OpenReview
remains available as a manual/local collector but is intentionally not scheduled in
GitHub Actions while unattended API access requires challenge verification. Expanded-source
workflows are deliberately staggered away from that pre-digest pair to reduce
contention in the shared repository-write concurrency group. A digest date is the
end date of the preceding 24-hour reporting window.

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
