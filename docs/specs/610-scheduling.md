# Scheduling Policy

**Status:** Active  
**Related tasks:** `FND-016`  
**Related decisions:** `D-103`, `D-108`

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
| OpenReview | 01:43, 07:43, 13:43, 19:43 daily | `43 4,10,16,22 * * *` |
| GitHub Discovery | 04:47, 16:47 daily | `47 7,19 * * *` |
| Daily Digest | 00:27 daily | `27 15 * * *` |

The daily digest run at 00:27 local time summarizes the previous
`Asia/Tokyo` calendar day.

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
