# State

- Roadmap phase: **0, walking skeleton** (ADR-0008) — CSV → Python → Snowflake `RAW` → dbt `stg_orders` → tests, on synthetic `orders`
- Current step: F0.1 done on its branch and reviewed; T-027 in progress (project in English, agent configuration local only, history rebuilt, remote recreated); then the F0.1 PR is reopened (T-021)
- Workspace: root of this repository
- Agent configuration: local only, not versioned (D-006, T-027); `memory/` is the only versioned record of the workflow
- Environment checked (2026-11-19): Git 2.56.0, Python 3.14.3 and 3.11, uv 0.11.3, pip 26.0.1, GitHub CLI authenticated (call it by full path in older sessions: `C:\Program Files\GitHub CLI\gh.exe`)
- Git: branch `main`, remote `origin` = **private** repository `ai-data-engineering-lab` on GitHub (recreated in T-027)
- Last update: 2026-11-19, coordinator
- Data: synthetic only, no PII (ADR-0002, ADR-0007)
- Language: everything in the repository is in English; nothing published carries tool attribution (T-027)

## Phase 0 features

| ID | Branch | Delivers |
| --- | --- | --- |
| F0.1 | `feature/f0-1-ingestion` | uv environment, synthetic generator, structural validation, quarantine, reconciliation, pytest |
| F0.2 | `feature/f0-2-dbt-staging` | dbt project in `transform/` with `dev` (DuckDB) and `snowflake` targets, `stg_orders`, dbt tests |
| F0.3 | `feature/f0-3-snowflake-raw-ci` | Minimal load into Snowflake `RAW` and GitHub Actions with pytest + dbt (DuckDB) |
| F0.4 | `feature/f0-4-orders-json` | Orders JSON, NAV and reconciliation with `orders` (ADR-0014) |

Coverage of the reference technical case: Task 1 → F0.2 (`org_summary`); Task 2 → F0.4; Task 3 → F0.1, F0.2 and ADR-0011; Task 4 → ADR-0010 and RB-001; Task 5 → ADR-0012.

## Latest result

F0.1 before T-027: the coordinator reran `uv run pytest` → 103 passed, exit 0; validator on the raw sample 284 = 272 + 12, exit 0; a 0xFF byte → exit 2 with only the file name. Reviewer and governance: nothing blocking. Confirmed by the coordinator: the byte position in the UTF-8 error is relative to the decoded chunk (20010 real, 3626 reported) → T-026. To be revalidated after the translation.

## Active constraints

Access constraints are in `memory/ACCESS.md`.
