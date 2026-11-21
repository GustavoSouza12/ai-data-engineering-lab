# ADR-0017 — Vertical-slice MVP

- Date: 2026-11-21
- Status: accepted (decided by the user on 2026-11-21); the reordered critical path is still pending the user's approval
- Changes: the roadmap in section 14 of `memory/architecture.md` (parts of phases 3 to 5 move forward) and ADR-0008 (sequence of the Snowflake load)

## Context
A planning review proposed an MVP as one thin vertical slice: ingestion → `RAW` → dbt staging/gold/marts with tests → orchestration with write-audit-publish (WAP) → CI. It raised five open calls (C1–C5) and twelve technical calls (T1–T12).

## Decision

### Open calls
- **C1 — target.** Not local-first only. DuckDB stays for dev and CI. The load into Snowflake `RAW` comes **right after the local slice runs**, not at the end, per ADR-0008, because the Snowflake trial expires. Snowflake work still requires the user's approval for credentials and credits.
- **C2 — CI/CD.** GitHub Actions CI only for now. No branch protection. CD comes when there is a Snowflake production target.
- **C3 — PII in `investors`.** Obviously fake placeholders; see ADR-0018.
- **C4 — scope.** The slice is approved as the MVP. It pulls parts of roadmap phases 3 (governance), 4 (Airflow, WAP) and 5 (CI) forward and introduces Astro (Astronomer Runtime) for Airflow.
- **C5 — off-contract header columns (T-026).** The file is rejected with exit code 2. A column without a `pii_level` never enters staging.

### Technical calls
| ID | Decision |
|---|---|
| T1 | Astro project at the repository root, with a strict `.dockerignore` |
| T2 | WAP publish macro through `adapter.dispatch`: on DuckDB a transactional swap that keeps the previous version for rollback; on Snowflake a real `SWAP` |
| T3 | The three planted semantic errors stay in gold, tested with `warn` + an `error_if` threshold + `store_failures` |
| T4 | Quarantine batch limit: 10% of input rows, configurable, in a testable module called by the DAG; validator exit codes unchanged |
| T5 | No CD in the MVP (C2). The pipeline check is the full DuckDB pipeline + `manifest.json` + a built Astro image, with no deploy |
| T6 | `fct_orders` materialized as a table |
| T7 | The mart is a view over published gold |
| T8 | "PII in a mart" means `restricted` columns; `confidential` is allowed in internal marts only |
| T9 | `org_summary` stays in `marts/internal/` |
| T10 | No Slack: structured log + `on_failure_callback` linking the runbook. No `sla_watchdog`, `governance_weekly` or dedicated backfill DAG in the MVP |
| T11 | Confirm the Astro Runtime Python version and Airflow 3 `logical_date` semantics during the orchestration tasks |
| T12 | Source timestamps are UTC. The DAG runs at 03:00 America/New_York and passes `--run-ts` in UTC; day rollover is tested |

## Rejected alternatives
- Local-first only, Snowflake at the end: the trial could expire before the real target is exercised.
- CD and branch protection now: there is no production target to deploy to.
- Allow or drop off-contract columns: an untagged column could carry PII.

## Consequences
The MVP tasks enter `memory/TASKS.md` from T-031 on, after the user approves the reordered critical path. The validator gains a new exit-2 case (C5).
