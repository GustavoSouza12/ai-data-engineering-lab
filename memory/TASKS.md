# Tasks

Task states: `pending`, `in progress`, `done`.

Test states, separate from task states: `proposed`, `executed`, `approved`.

Commit hashes from before T-027 refer to the old history, which was rebuilt; they are kept only as a record.

## Tasks

| ID | Owner | Description | State | Blocker / evidence |
| --- | --- | --- | --- | --- |
| T-001 | Coordinator | Create the local folder, git and the workflow files | done | — |
| T-002 | Coordinator | Confirm that builder, reviewer and governance are loaded as subagents by the agent runtime | done | Evidence (2026-11-19): the session's agent list shows all three with the right tools; a delegated governance run used only read/search/list tools and returned a report |
| T-003 | Coordinator | Receive the goal, propose the plan and wait for approval | done | Goal set as phase 0 (ADR-0002 to ADR-0005) |
| T-004 | Coordinator | Migrate the agent configuration to the new runtime (D-006) | done | — |
| T-005 | Coordinator | Define the CSV contract | done | ADR-0002 and ADR-0003, then ADR-0009 |
| T-008 | Coordinator | Apply the governance findings from the T-002 test | done | Approved by the user on 2026-11-19 |
| T-009 | User | Install and authenticate the GitHub CLI | done | Evidence: `gh auth status` ok, scopes `repo` and `workflow` |
| T-010 | Coordinator | Base commit on `main`, private repository and first push | done | Evidence: `gh repo view` → `PRIVATE`, default branch `main` |
| T-011 | Builder | F0.1 — ingestion: uv environment, synthetic generator, validation, quarantine, reconciliation, pytest | done | Branch `feature/f0-1-ingestion` |
| T-012 | Reviewer + Governance | Review F0.1 on the diff | done | No blocking findings. Reviewer: A1–A8; governance: personal email in author metadata (A-1). A1 reproduced by the coordinator |
| T-017 | Builder | F0.1 rework: versioning (ADR-0009) + A1 (`extra_fields`, no orphan `.tmp`, exit code 3 for unexpected errors) + A4, A5, A6, A7 | done | Checked by the coordinator: 79 passed (exit 0); validator 284 = 272 + 12 |
| T-018 | User | Decide the commit email | done | Keep the personal email (2026-11-19): personal portfolio repository. Treat the lab as if it were real |
| T-019 | Coordinator | Quarantine flow ADR | done | ADR-0011 |
| T-020 | Reviewer + Governance | Review the F0.1 rework | done | Nothing blocking. Reviewer F1–F6 (F2 reproduced: invalid UTF-8 exited with 3; F5 checked: raw = generator byte for byte). Governance G-1–G-3 (logs) |
| T-025 | Builder | Short round before the PR: test + README for rule F1, invalid UTF-8/unreadable CSV → exit 2 (F2), README without a false ordering claim (F4), unexpected error without exception text outside `--debug` (G-1), only the file name in messages (G-2) | done | Approved by the user ("short round and PR", 2026-11-19). Checked by the coordinator: 103 passed (exit 0); 284 = 272 + 12; F1 was already the code's behavior (test + README only). Reviewer and governance: nothing blocking |
| T-027 | Coordinator + Builder | Whole project in English and no tool attribution on GitHub: translate code, tests, docs and `memory/`; keep the agent configuration local only; rebuild a short English history; delete and recreate the remote repository | done | User's decision (2026-11-19): delete and recreate the repo, new short history, agent configuration out of the repo, agents renamed to builder/reviewer/governance. Evidence: old repository deleted (0 forks), recreated as private, only `main` and the feature branch pushed, no tags; no tool attribution found in the PR, commits or tree on GitHub |
| T-021 | Coordinator | Open the F0.1 PR | done | PR #1 on the recreated repository: https://github.com/GustavoSouza12/ai-data-engineering-lab/pull/1. Merge only by the user; squash recommended; no CI until F0.3 |
| T-028 | Builder | Pre-merge round on PR #1 (reviewer findings): translate the `.gitattributes` comment without touching the `-text` rule; README "Known limitations" line about the UTF-8 error byte position (T-026); drop the unused `exc` in `normalize_run_ts`. The `--debug` "Unsafe" help and the `--run-ts` no-echo stay in this PR | done | Approved by the user (2026-11-19). Builder commit `1ea989d` (3 files, +5/−2). Checked by the coordinator: 104 passed, exit 0; 284 = 272 + 12; no non-ASCII text outside `memory/`, `data/` and `uv.lock` |
| T-026 | Builder | F0.1 follow-up queue (not blocking): the byte position in the UTF-8 error is relative to the decoded chunk (confirmed: 20010 real, 3626 reported) → report the line or read as bytes; a column outside the contract in the header reaches staging without a `pii_level` (needs a decision: reject, drop or allow-list; ADR-0014); reserved names (`_source_file`, `_loaded_at`, `reject_reason`) or a duplicate header → exit 2. The `--debug` help warning and the `--run-ts` message without echo were done in T-027 | pending | Extra columns decided (2026-11-21): reject the file with exit 2 (ADR-0017, C5). F0.1 merged |
| T-013 | Builder | F0.2a — dbt-duckdb project in `transform/` (`dev` target only; `snowflake` target arrives with F0.3): `organizations` and `fx_rates` seeds, `orders` source on `data/staging/orders/`, `stg_orders`, `int_orders__latest`, `fct_orders` with `amount_usd`, `org_summary` (case Task 1, without completion dates), dbt tests TS-008 to TS-012, TS-019, TS-020 (orders → organizations and fx_rates only), TS-021; one local command that runs generator → validator → `dbt build`. Review requirements: `trim` before deduplicating (F3); detect conflicts across daily files (same version, different content) as a dbt test; `--debug` never enabled in a DAG (G-3) | pending | Scope approved by the user (2026-11-19, "F0.2a lean"). Starts from `main` after the user merges PR #1 |
| T-029 | Builder | F0.2b — `order_events` (ADR-0015): generator, source, `stg_order_events`, completion dates in `org_summary`, status × latest event consistency test, TS-020 events part | pending | F0.2a merge |
| T-014 | Builder | F0.3 — minimal load into Snowflake `RAW` (data and quarantine) and CI on GitHub Actions | pending | F0.2 merge and T-015 |
| T-015 | User | Snowflake account (Enterprise) and credentials outside the repository | in progress | Evidence (2026-11-19): keys under the user profile, outside the repo; `SHOW USERS LIKE 'LAB_%'` shows `LAB_DBT_SVC` and `LAB_LOADER_SVC` (user's screenshot); `SNOWFLAKE_ACCOUNT` and `SNOWFLAKE_KEYS_DIR` variables set. Pending: real connection (F0.3) and Enterprise edition |
| T-016 | Builder | Version the Snowflake bootstrap in `infra/snowflake/` | pending | Part of F0.3 |
| T-022 | Builder | F0.4 — orders JSON (investor, product, status, NAV), parsing, NAV `LAG` and reconciliation with `orders` (case Task 2, ADR-0014) | pending | F0.3 merge |
| T-023 | Coordinator | Runbook RB-001 (a metric jumped) | done | `memory/runbooks/RB-001-metric-jumped.md` |
| T-024 | Coordinator | Technical case ADRs: 0009 to 0014 | done | 2026-11-19 |
| T-030 | Ship | MVP-00: bring `1ea989d` and `aac6e18` (pushed to `feature/f0-1-ingestion` after the PR #1 squash) to `main`; update `STATE.md`; ADR-0016 (Firstmate runtime, amends ADR-0006), ADR-0017 (vertical-slice MVP), ADR-0018 (synthetic PII, amends ADR-0002); `agent-workflow.md`; `ACCESS.md` | in progress | Decided by the user (2026-11-21). Branch `feature/t-030-sync-main-and-adrs`; on this branch the two commits are `48ad7da` and `f85bf9d`, trees identical to the originals. Architecture and governance Scout reviews follow |

## Tests

| ID | Feature | Description | State | Evidence |
| --- | --- | --- | --- | --- |
| TS-001 | F0.1 | A complete record with a unique key goes to staging | executed | revalidated on `1ea989d` (tree `6f96732`, after T-028): 104 passed, exit 0; 284 = 272 + 12. After the squash merge, check that `main^{tree}` differs from this tree only in `memory/` |
| TS-002 | F0.1 | A required field that is empty or whitespace-only goes to quarantine with a `reject_reason` | executed | same as TS-001 |
| TS-003 | F0.1 | ~~Every occurrence of a duplicate `order_id` goes to quarantine~~ replaced by TS-013 to TS-015 (ADR-0009) | replaced | — |
| TS-004 | F0.1 | A required column missing from the header gives a clear error, with no partial output | executed | same as TS-001 |
| TS-005 | F0.1 | A header-only file produces empty outputs, with no error | executed | same as TS-001 |
| TS-006 | F0.1 | Running twice produces identical outputs (idempotency) | executed | same as TS-001 |
| TS-007 | F0.1 | Reconciliation: input rows = staging + quarantine | executed | same as TS-001 |
| TS-013 | F0.1 | Versions (same `order_id`, different `updated_at`) all go to staging | executed | same as TS-001 |
| TS-014 | F0.1 | Exact duplicates go to staging (dedup belongs to dbt) | executed | same as TS-001 |
| TS-015 | F0.1 | Conflict (same `order_id` and `updated_at`, different content) → every occurrence in quarantine with `conflicting_version` | executed | same as TS-001 |
| TS-016 | F0.1 | A row with extra fields → quarantine `extra_fields`, no orphan `.tmp` (A1) | executed | same as TS-001 |
| TS-017 | F0.1 | An unexpected error exits with code 3, distinct from reconciliation (1) and invalid input (2) | executed | same as TS-001 |
| TS-018 | F0.1 | `--staging-dir`/`--quarantine-dir` equal to each other or to the input folder are refused (A6) | executed | same as TS-001 |
| TS-023 | F0.1 | T-025 round: F1 (incomplete row with the key of a complete one → both in quarantine), F2 (invalid UTF-8/unreadable CSV → exit 2, no partial output), F4 (header order not required), G-1 (no exception text outside `--debug`), G-2 (file name only); T-027: invalid `--run-ts` exits 2 without echoing the value, `--debug` help warns it is unsafe | executed | same as TS-001 |
| TS-024 | F0.1 | Correct invalid-byte position above 8 KB; column outside the contract, reserved name and duplicate header handled (T-026) | proposed | — |
| TS-008 | F0.2 | dbt: `fct_orders` grain — `order_id` `unique` and `not_null` | proposed | — |
| TS-009 | F0.2 | dbt: `channel`, `currency` and `status` within accepted values | proposed | — |
| TS-010 | F0.2 | dbt: `amount` castable and > 0 | proposed | — |
| TS-011 | F0.2 | dbt: count and sum (per currency) match between staging and gold | proposed | — |
| TS-012 | F0.2 | dbt: `submitted_at` ≤ `updated_at` ≤ file date | proposed | — |
| TS-019 | F0.2 | dbt: `int_orders__latest` has one row per `order_id`, the one with the latest `updated_at` | proposed | — |
| TS-020 | F0.2 | dbt: `relationships` — every order has an organization; every event has an order; every order has an exchange rate | proposed | — |
| TS-021 | F0.2 | dbt: `org_summary` keeps organizations without orders and does not inflate amounts (gold sum = summary sum) | proposed | — |
| TS-022 | F0.4 | JSON: one row per order; previous NAV via `LAG`; JSON × `orders` divergences become issues | proposed | — |

A test only becomes `approved` with the user's explicit acceptance.

## Open items

- T-030 PR: architecture and governance Scout reviews, then merge by the user.
- User approval of the reordered MVP critical path (ADR-0017, C1); then the MVP tasks enter this file from T-031.
- Columns outside the contract in the header (T-026): decided, reject with exit 2 (ADR-0017, C5); implementation pending.
- Acceptance of the F0.1 tests after review.
