# ADR-0008 — Walking skeleton in phase 0

- Date: 2026-11-19
- Status: accepted (user's choice)
- Changes: the roadmap in section 14 of `memory/architecture.md` (order of phases 0 to 2) and ADR-0004 (DuckDB is no longer the only target)

## Context
The roadmap builds one layer per phase: Python (0), Snowflake (1), dbt (2). That way, integration between the pieces only shows up late. The lab's goal is to see the real AI Data Engineering flow end to end.

## Decision
Phase 0 delivers a thin, complete path: CSV → Python ingestion → Snowflake `RAW` → dbt `stg_orders` → tests.

| Feature | Delivers |
|---|---|
| F0.1 | Python ingestion, quarantine, reconciliation, pytest (unchanged) |
| F0.2 | dbt project in `transform/` with two targets: `dev` (DuckDB, local and CI) and `snowflake` |
| F0.3 | Minimal load into Snowflake `RAW` (stage → `COPY INTO`, `_loaded_at`) and CI with pytest + dbt on DuckDB |

Phase 1 functional roles, dedicated warehouses and resource monitors still come later, but the skeleton already goes through Snowflake.

## Credentials
- Never in the repository. They live in environment variables or in a `profiles.yml` outside the project folder.
- The dbt service user authenticates with a key pair; the private key stays outside the repository.
- The coordinator and the agents never read or display credentials. Governance checks this on every PR.

## Rejected alternatives
- Layer by layer: integration discovered late.
- DuckDB only in phase 0: hides the real Snowflake differences.

## Consequences
F0.3 depends on the user's Snowflake account. Model SQL must run on both targets.
