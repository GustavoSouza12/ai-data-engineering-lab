# State

- Roadmap phase: **0, walking skeleton** (ADR-0008), moving to the vertical-slice MVP (ADR-0017)
- Current step: F0.1 merged (PR #1, squash `bd6af53`). T-030 brings T-028 and the approved F0.2a scope to `main` and records ADR-0016 to ADR-0018. Critical path approved (ADR-0017). Next: MVP-01, which adds the MVP backlog to `TASKS.md` from T-031; the Snowflake `RAW` load (MVP-15a) comes right after MVP-06, before the trial ends around 2026-12-11
- Workspace: root of this repository
- Agent runtime: Firstmate (ADR-0016): first mate, Ship crewmate, architecture and governance Scouts. Flow in `memory/agent-workflow.md`. Agent configuration is local only, not versioned (D-006, T-027)
- Environment: the earlier Windows setup (Git 2.56.0, Python 3.11, uv 0.11.3, GitHub CLI) was checked on 2026-11-19 by the previous runtime. On the Firstmate machine (2026-11-21) uv and pytest are not installed yet
- Git: branch `main`, remote `origin` = **private** repository `ai-data-engineering-lab` on GitHub (recreated in T-027). No CI and no branch protection yet (ADR-0017, C2)
- Last update: 2026-11-21, Ship crewmate under the first mate (T-030)
- Data: synthetic only; PII-shaped columns use obvious placeholders (ADR-0002, ADR-0007, ADR-0018)
- Language: everything in the repository is in English; nothing published carries tool attribution (T-027, ADR-0016)

## Phase 0 features

| ID | Branch | Delivers |
| --- | --- | --- |
| F0.1 | `feature/f0-1-ingestion` | uv environment, synthetic generator, structural validation, quarantine, reconciliation, pytest (merged, PR #1) |
| F0.2a | `feature/f0-2-dbt-staging` | dbt-duckdb project in `transform/`: seeds, `stg_orders`, `int_orders__latest`, `fct_orders` (`amount_usd`), `org_summary`, dbt tests, one end-to-end local command (T-013) |
| F0.2b | `feature/f0-2b-order-events` | `order_events` and completion dates (T-029, ADR-0015) |
| F0.3 | `feature/f0-3-snowflake-raw-ci` | Minimal load into Snowflake `RAW` and GitHub Actions with pytest + dbt (DuckDB) |
| F0.4 | `feature/f0-4-orders-json` | Orders JSON, NAV and reconciliation with `orders` (ADR-0014) |

These features will be mapped into the MVP backlog (ADR-0017) when it enters `TASKS.md`.

Coverage of the reference technical case: Task 1 → F0.2 (`org_summary`); Task 2 → F0.4; Task 3 → F0.1, F0.2 and ADR-0011; Task 4 → ADR-0010 and RB-001; Task 5 → ADR-0012.

## Latest result

PR #1 (https://github.com/GustavoSouza12/ai-data-engineering-lab/pull/1) was squash-merged as `bd6af53` with the tree of `4334145`. Two commits pushed to `feature/f0-1-ingestion` after that tree never reached `main`: `1ea989d` (T-028) and `aac6e18` (T-028 record, F0.2a scope, T-029). T-030 cherry-picks both unchanged; their trees match the originals. Last test run of F0.1 (previous runtime, on `1ea989d`): 104 passed, exit 0; 284 = 272 + 12.

## Active constraints

Access constraints are in `memory/ACCESS.md`.
