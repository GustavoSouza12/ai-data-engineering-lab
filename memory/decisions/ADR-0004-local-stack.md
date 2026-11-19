# ADR-0004 — Phase 0 local stack

- Date: 2026-11-19
- Status: accepted (decision delegated by the user to the coordinator); partially changed by ADR-0008 (Snowflake becomes a second target in phase 0)

## Context
The roadmap asks for pytest, and the user wants to see dbt tests already in phase 0. Snowflake only arrives in phase 1. Environment checked on 2026-11-19: Python 3.14.3 and 3.11 installed, `uv` 0.11.3, `pip` 26.0.1.

## Decision
- Virtual environment `.venv` created with `uv` on **Python 3.11** (assumption to confirm at install time: dbt may not support 3.14 yet).
- Dependencies in `pyproject.toml`, versions locked in `uv.lock`: `pytest`, `dbt-core`, `dbt-duckdb`.
- **DuckDB stands in for Snowflake in phase 0.** dbt models must use portable SQL so they can move in phase 1.
- Synthetic data generated with the standard library (`random` with a fixed seed), no Faker.

## Rejected alternatives
- `unittest`: installs nothing, but diverges from the roadmap and from the architecture's CI.
- Snowflake already in phase 0: requires an account and credentials before the flow is proven.

## Consequences
Installing dependencies is part of the F0.1 scope. SQL differences between DuckDB and Snowflake will be handled in phase 1.
