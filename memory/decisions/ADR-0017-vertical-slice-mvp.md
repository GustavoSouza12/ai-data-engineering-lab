# ADR-0017 — Vertical-slice MVP

- Date: 2026-11-21
- Status: accepted (decided by the user on 2026-11-21); critical path approved on 2026-11-21
- Changes: the roadmap in section 14 of `memory/architecture.md` (parts of phases 3 to 5 move forward) and ADR-0008 (feature sequence: the Snowflake `RAW` load is placed by the MVP critical path below instead of F0.3)

## Context
A planning review proposed an MVP as one thin vertical slice: ingestion → `RAW` → dbt staging/gold/marts with tests → orchestration with write-audit-publish (WAP) → CI, as items MVP-00 to MVP-17. It raised five open calls (C1–C5) and twelve technical calls (T1–T12).

## Decision

### Open calls
- **C1 — target.** Not local-first only. DuckDB stays for dev and CI. ADR-0008's principle holds (the skeleton goes through Snowflake early), but the load into Snowflake `RAW` comes **right after the local slice runs** (MVP-15a, right after MVP-06 in the critical path below), not at the end, because the Snowflake trial expires. Snowflake work still requires the user's approval for credentials and credits.
- **C2 — CI/CD.** GitHub Actions CI only for now. No branch protection. CD comes when there is a Snowflake production target.
- **C3 — PII in `investors`.** Obviously fake placeholders; see ADR-0018.
- **C4 — scope.** The slice is approved as the MVP. It pulls parts of roadmap phases 3 (governance), 4 (Airflow, WAP) and 5 (CI) forward and introduces Astro (Astronomer Runtime) for Airflow.
- **C5 — off-contract header columns (T-026).** For CSV sources, the file is rejected with exit code 2. A column without a `pii_level` never enters staging.

### Technical calls
| ID | Decision |
|---|---|
| T1 | Astro project at the repository root, with a strict `.dockerignore` |
| T2 | WAP publish macro through `adapter.dispatch`: on DuckDB a transactional swap that keeps the previous version for rollback; on Snowflake a real `SWAP` |
| T3 | The three planted semantic errors stay in gold, tested with `warn` + an `error_if` threshold + `store_failures` |
| T4 | Quarantine batch limit: 10% of input rows, configurable, in a testable module called by the DAG; validator exit codes unchanged |
| T5 | The planning recommendation was an MVP "CD" made of the full DuckDB pipeline + `manifest.json` + a built Astro image, with no deploy. Adjusted to C2: this is a CI check only; there is no CD in the MVP for now |
| T6 | `fct_orders` materialized as a table |
| T7 | The mart is a view over published gold |
| T8 | "PII in a mart" means `restricted` columns; `confidential` is allowed in internal marts only |
| T9 | `org_summary` stays in `marts/internal/` |
| T10 | No Slack: structured log + `on_failure_callback` linking the runbook. No `sla_watchdog`, `governance_weekly` or dedicated backfill DAG |
| T11 | Confirm the Astro Runtime Python version and Airflow 3 `logical_date` semantics in MVP-09 and MVP-10 |
| T12 | Source timestamps are declared UTC. The DAG runs at 03:00 America/New_York and passes `--run-ts` in UTC; day rollover is tested |

### Critical path (approved by the user on 2026-11-21)
MVP-00 → MVP-01 → MVP-02 → MVP-03 → MVP-04 → MVP-06 → **MVP-15a** (Snowflake `RAW` load, pulled forward to right after MVP-06) → MVP-07 → MVP-08 → **MVP-15b** (real Snowflake `SWAP`, stays after MVP-07) → MVP-05 → MVP-09 → MVP-10 → MVP-13 → MVP-14 → MVP-16 → MVP-17.

MVP-11 (CD) and MVP-12 (`main` protection) are out of the MVP for now (C2).

Reason: the Snowflake trial ends around 2026-12-11. The account is Enterprise edition, so MVP-16 (tag-based masking) can be proven within the trial. The user prepares the T-015 service users and keys while MVP-02 to MVP-08 run. Each Snowflake step still needs the user's approval for credentials and credit spend.

## Rejected alternatives
- Local-first only, Snowflake at the end: the trial could expire before the real target is exercised.
- CD and branch protection now: there is no production target to deploy to.
- Allow or drop off-contract CSV columns: an untagged column could carry PII.

## Consequences
The MVP items enter `memory/TASKS.md` from T-031 on, in MVP-01, each with its scope. The validator gains a new exit-2 case (C5). C5 covers CSV headers only; the JSON new-field policy of ADR-0014 is unchanged.
