# ADR-0011 — Quarantine, data quality issues and notification

- Date: 2026-11-19
- Status: accepted as a design (T-019); implemented in phases 0.3 (quarantine table in RAW), 3 (tags and owners) and 4 (issues and notification)
- Diagrams: `memory/architecture.md`, sections 3.2 and 3.3

## Decision
1. **Quarantine in RAW:** `RAW.<source>.<TABLE>_QUARANTINE` stores the raw row with `reject_reason`, `_source_file` and `_loaded_at`, and **inherits the source's PII tags and restricted access**.
2. **Semantic failures:** dbt tests with `store_failures` into `ANALYTICS.DQ_FAILURES`.
3. **Issues:** `OPS.DATA_QUALITY.DQ_ISSUES`, one row per problem, key `issue_key = hash(rule, entity)`, updated by `MERGE` on every run (even when the audit fails). States: `open`, `acknowledged`, `resolved` (automatic when the rule stops failing), `wont_fix` (with a justification), `escalated` (open for more than 7 days).
4. **Owners:** `GOVERNANCE.ENTITLEMENTS.DQ_OWNERS` maps a rule or source to the owning team, changed only through PRs.
5. **Notification:** through Airflow, not Snowflake, to keep orchestration in one place. The email carries the count, rule, IDs and a dashboard link; **never** the row content.
6. **Block or publish:** each test defines `warn_if` (publish and warn) and `error_if` (do not publish).
7. **Leadership metric:** open issues by owner and age, and time to resolve.

## Rejected alternatives
- Drop invalid rows: loses evidence and prevents auditing.
- Send the rows by email: takes PII outside access control.
- One issue row per run: repeated alerts and alert fatigue.
