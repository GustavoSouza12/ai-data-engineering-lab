# Tasks

Task states: `pending`, `in progress`, `done`, `deferred` (out of the current scope by a recorded decision).

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
| T-026 | Builder | F0.1 follow-up queue (not blocking): the byte position in the UTF-8 error is relative to the decoded chunk (confirmed: 20010 real, 3626 reported) → report the line or read as bytes; a column outside the contract in the header reaches staging without a `pii_level` (decided: reject the file, exit 2; ADR-0017 C5); reserved names (`_source_file`, `_loaded_at`, `reject_reason`) or a duplicate header → exit 2. The `--debug` help warning and the `--run-ts` message without echo were done in T-027 | pending | Extra columns decided (2026-11-21): reject the file with exit 2 (ADR-0017, C5). F0.1 merged. The header hardening (off-contract, reserved and duplicate columns) is absorbed by MVP-04 (T-034); the UTF-8 byte position stays here |
| T-013 | Builder | F0.2a — dbt-duckdb project in `transform/` (`dev` target only; `snowflake` target arrives with F0.3): `organizations` and `fx_rates` seeds, `orders` source on `data/staging/orders/`, `stg_orders`, `int_orders__latest`, `fct_orders` with `amount_usd`, `org_summary` (case Task 1, without completion dates), dbt tests TS-008 to TS-012, TS-019, TS-020 (orders → organizations and fx_rates only), TS-021; one local command that runs generator → validator → `dbt build`. Review requirements: `trim` before deduplicating (F3); detect conflicts across daily files (same version, different content) as a dbt test; `--debug` never enabled in a DAG (G-3) | pending | Scope approved by the user (2026-11-19, "F0.2a lean"). Unblocked (PR #1 merged); will be remapped into the MVP backlog (ADR-0017). Absorbed by MVP-02 (T-032) |
| T-029 | Builder | F0.2b — `order_events` (ADR-0015): generator, source, `stg_order_events`, completion dates in `org_summary`, status × latest event consistency test, TS-020 events part | pending | F0.2a merge. Not on the MVP critical path (ADR-0017); after the MVP |
| T-014 | Builder | F0.3 — minimal load into Snowflake `RAW` (data and quarantine) and CI on GitHub Actions | pending | Split by ADR-0017: CI moves to MVP-03 (T-033), the `RAW` load to MVP-15a (T-045) |
| T-015 | User | Snowflake account (Enterprise) and credentials outside the repository | done | Evidence (2026-11-21, reported by the user): both service users (`LAB_DBT_SVC`, `LAB_LOADER_SVC`) created; their keys are on the WSL machine, outside the repo, with fingerprints verified; the account and key-directory environment variables are configured; uv is installed on the WSL machine. The account is an Enterprise-edition trial ending around 2026-12-11. The real connection is exercised in MVP-15a (T-045) |
| T-016 | Builder | Version the Snowflake bootstrap in `infra/snowflake/` | pending | Absorbed by MVP-15a (T-045). The user has a local `bootstrap.sql` outside the repo to use as the base; it is not copied into the repo by agents |
| T-022 | Builder | F0.4 — orders JSON (investor, product, status, NAV), parsing, NAV `LAG` and reconciliation with `orders` (case Task 2, ADR-0014) | pending | F0.3 merge. Not on the MVP critical path (ADR-0017); after the MVP |
| T-023 | Coordinator | Runbook RB-001 (a metric jumped) | done | `memory/runbooks/RB-001-metric-jumped.md` |
| T-024 | Coordinator | Technical case ADRs: 0009 to 0014 | done | 2026-11-19 |
| T-030 | Ship | MVP-00: bring `1ea989d` and `aac6e18` (pushed to `feature/f0-1-ingestion` after the PR #1 squash) to `main`; update `STATE.md`; ADR-0016 (Firstmate runtime, amends ADR-0006), ADR-0017 (vertical-slice MVP), ADR-0018 (synthetic PII, amends ADR-0002); `agent-workflow.md`; `ACCESS.md` | done | Decided by the user (2026-11-21). Merged: PR #2 (https://github.com/GustavoSouza12/ai-data-engineering-lab/pull/2), squash `38f40ec` |
| T-031 | Ship | MVP-01: add the MVP backlog (T-031 to T-048) and its acceptance tests (TS-025 onwards) to this file; record T-015 done; note the T-016 base | in progress | Branch `feature/mvp-01-tasks-backlog`, on `main`. ADR-0017 already records C1–C5 and T1–T12 |
| T-032 | Builder | MVP-02: F0.2a dbt-duckdb project in `transform/`, exactly the T-013 scope: seeds, `stg_orders` (`trim` before dedup, 272 → 270), `int_orders__latest` (190), `fct_orders` as a table (T6) with `amount_usd`, `org_summary` (20 orgs), dbt tests; the 3 planted errors (`ORD-00047`, `ORD-00123`, `ORD-00084`) stay in gold with `warn` + `error_if` threshold + `store_failures` (T3), so `dbt build` exits 0 with 3 warnings; cross-file conflict test; `meta.pii_level` on every column; one local command generator → validator → `dbt build` | pending | Absorbs T-013. Depends on MVP-01 |
| T-033 | Builder | MVP-03: GitHub Actions CI on `pull_request`: `uv sync --frozen`, ruff, pytest, sqlfluff, `dbt build --target dev` on DuckDB; `contents: read`, pinned actions, no `secrets.`, concurrency cancel; red/green evidence | pending | Depends on MVP-02. Takes the CI part of T-014. CI only, no CD (C2) |
| T-034 | Builder | MVP-04: validator `--summary-json` (counts and reason codes, no row values); batch guard module + CLI failing above 10% quarantined rows, configurable (T4); header hardening: off-contract column → exit 2 (C5), reserved name or duplicate header → exit 2; exit codes 0/1/2/3 unchanged | pending | Absorbs the header part of T-026. Depends on MVP-01 |
| T-036 | Builder | MVP-06: local DuckDB `RAW` (`raw.orders`, `raw.orders_quarantine`), text columns + `_source_file`/`_loaded_at`; idempotent per `_source_file` in one transaction; load reconciliation with rollback; dbt source moves to `raw.orders` with the same MVP-02 results | pending | Depends on MVP-02 and MVP-04. First local end-to-end run is reached here |
| T-045 | Builder + User | MVP-15a: minimal Snowflake bootstrap in `infra/snowflake/` (databases, roles, XS warehouses, resource monitor with a credit quota) applied by the user, and idempotent load into `RAW` (272/12 for the sample) | pending | Absorbs T-016 and the `RAW` part of T-014. Pulled forward to right after MVP-06 (trial ends around 2026-12-11). Needs the user's approval for credentials and credits; agents never read keys |
| T-037 | Builder | MVP-07: local WAP for gold: write to `gold_staging`, audit (tests + count/sum reconciliation, TS-011), `publish_gold` via `adapter.dispatch` (DuckDB transactional swap keeping the previous version; Snowflake `SWAP` reviewed, not run), `rollback_gold`, rerun checksum identical | pending | Depends on MVP-06 |
| T-038 | Builder | MVP-08: `org_summary` mart in `models/marts/internal/` (T9) as a view over published gold (T7), never `gold_staging`; no `restricted` columns (T8) | pending | Depends on MVP-07 |
| T-046 | Builder + User | MVP-15b: `dbt build --target snowflake` + real `ALTER SCHEMA … SWAP`; failed audit leaves gold's hash unchanged; grants survive `SWAP` on both schemas, and so do MVP-16's tags and policies once they exist | pending | Depends on MVP-07 and MVP-15a. Needs the user's approval for credentials and credits |
| T-035 | Builder | MVP-05: generator by logical date (`--date`), date-derived seed, default date byte-identical to the sample; D+1 has new versions, new orders, a late version, and a cross-file conflict only with `--plant-cross-file-conflict` (ADR-0009, amendment 2026-11-23); stdlib only | pending | Depends on MVP-00 |
| T-039 | Builder | MVP-09: local Astro project at the repo root (T1) with strict `.dockerignore`, pinned Astro Runtime and Cosmos, dbt in a separate venv, mounted volume for DuckDB and `data/`; no credentials in `airflow_settings.yaml`; runtime Python documented (T11) | pending | Depends on MVP-01 and MVP-02. Also amends the `architecture.md` roadmap and the ADR-0005 layout for Astro. Downloads only, no deploy |
| T-040 | Builder | MVP-10: `daily_platform` DAG (MVP version) + backfill: sensor → validate → batch guard → load `RAW` → dbt on `gold_staging` → reconcile → publish → mart → notify (log only, T10); 03:00 America/New_York, `--run-ts` in UTC from the logical date (T12); `max_active_runs=1`; failure paths leave gold unchanged | pending | Depends on MVP-05, MVP-07, MVP-08, MVP-09 |
| T-041 | Builder | MVP-11: CD on `main` | deferred | Out of the MVP for now (ADR-0017, C2): no production target |
| T-042 | Builder + User | MVP-12: `main` protection, CODEOWNERS and PR template | deferred | Out of the MVP for now (ADR-0017, C2) |
| T-043 | Coordinator + Builder | MVP-13: synthetic `investors` source to `dim_investor`: contract with `pii_level` per column, stdlib generator with obvious placeholders (ADR-0018), ingestion with the `orders` guarantees, `dim_investor` through WAP, no `restricted` values in any output or log | pending | Depends on MVP-01, MVP-06, MVP-07 |
| T-044 | Builder | MVP-14: local governance guard over `manifest.json` (valid `pii_level`, gold PK/description/owner, no `restricted` in marts) run in CI; `apply_pii_tags` post-hook (no-op on DuckDB, `SET TAG` on Snowflake, run only in MVP-16) | pending | Depends on MVP-13 and MVP-03 |
| T-047 | Builder + User | MVP-16: Snowflake `PII_LEVEL` tag and tag-based masking on `investors` (`RAW`, quarantine, `GOLD`, `GOLD_STAGING`); `ANALYST` sees masked values, `TRANSFORMER` clear; survives `SWAP` | pending | Depends on MVP-14 and MVP-15b. Enterprise trial. New scope pulled forward from roadmap phase 3 (ADR-0017, C4). Needs the user's approval |
| T-048 | Coordinator + User | MVP-17: runbook RB-002, clean-clone demo script, every MVP test `executed`, user acceptance | pending | Depends on all approved MVP tasks |

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
| TS-024 | F0.1 | Correct invalid-byte position above 8 KB; column outside the contract, reserved name and duplicate header handled (T-026); the header part is covered by TS-029 (MVP-04) | proposed | — |
| TS-008 | F0.2 | dbt: `fct_orders` grain — `order_id` `unique` and `not_null` | proposed | — |
| TS-009 | F0.2 | dbt: `channel`, `currency` and `status` within accepted values | proposed | — |
| TS-010 | F0.2 | dbt: `amount` castable and > 0 | proposed | — |
| TS-011 | F0.2 | dbt: count and sum (per currency) match between staging and gold | proposed | — |
| TS-012 | F0.2 | dbt: `submitted_at` ≤ `updated_at` ≤ file date | proposed | — |
| TS-019 | F0.2 | dbt: `int_orders__latest` has one row per `order_id`, the one with the latest `updated_at` | proposed | — |
| TS-020 | F0.2 | dbt: `relationships` — every order has an organization; every event has an order; every order has an exchange rate | proposed | — |
| TS-021 | F0.2 | dbt: `org_summary` keeps organizations without orders and does not inflate amounts (gold sum = summary sum) | proposed | — |
| TS-022 | F0.4 | JSON: one row per order; previous NAV via `LAG`; JSON × `orders` divergences become issues | proposed | — |
| TS-025 | MVP-02 | dbt build on the sample: 270 staging rows after `trim`+dedup, 190 in `int_orders__latest` and `fct_orders`, 20 in `org_summary`; exits 0 with exactly 3 warnings (`ORD-00047`, `ORD-00123`, `ORD-00084`) | proposed | — |
| TS-026 | MVP-02 | Cross-file conflict (same version, different content, different `_source_file`) with a 2-file fixture: every occurrence in `dq_orders_cross_file_conflicts` (`conflicting_version_cross_file`), the order out of gold, the others published; the test warns and errors only above `cross_file_conflict_error_threshold` conflicted orders of the newest batch (ADR-0009, amendment 2026-11-23) | proposed | — |
| TS-027 | MVP-03 | CI is red on a PR with a broken dbt test and green on a normal PR; workflow has no `secrets.` reference | proposed | — |
| TS-028 | MVP-04 | `--summary-json` has counts and reason codes and no field values; batch guard: sample (12/284) passes, 30% fixture fails, header-only passes | proposed | — |
| TS-029 | MVP-04 | Off-contract header column, reserved name or duplicate header → exit 2 with no output; previous tests still pass (covers the header part of TS-024) | proposed | — |
| TS-030 | MVP-06 | `RAW` load: rerun gives the same counts (272/12), two days coexist, a mid-transaction failure leaves nothing partial, mismatched reconciliation rolls back with exit ≠ 0 | proposed | — |
| TS-031 | MVP-07 | WAP: publish makes `gold` equal `gold_staging` (190); injected audit failure blocks publish and keeps the gold checksum; rollback restores it; rerun checksum identical | proposed | — |
| TS-032 | MVP-08 | Mart is a view over `gold` (never `gold_staging`), 20 rows, sum = gold sum, no `restricted` column | proposed | — |
| TS-033 | MVP-15a | Snowflake `RAW` load idempotent per `_source_file` (272/12 on rerun); resource monitor quota visible | proposed | — |
| TS-034 | MVP-15b | Snowflake `SWAP`: `GOLD.FCT_ORDERS` 190 rows; failed audit leaves `HASH_AGG(*)` unchanged | proposed | — |
| TS-035 | MVP-05 | Same date → same bytes; default date byte-identical to the sample; D+1 contains the late version, and the cross-file conflict only with `--plant-cross-file-conflict` | proposed | — |
| TS-036 | MVP-09 | `astro dev parse` exits 0; integrity test passes and Cosmos renders one task per model | proposed | — |
| TS-037 | MVP-10 | DAG runs for 2026-11-19, rerun and 3-date backfill; above-limit file, missing file and forced audit failure leave gold unchanged; no `datetime.now()` or `--debug` in the DAG | proposed | — |
| TS-038 | MVP-13 | `dim_investor` 60 rows, PK tests and `relationships` from `fct_orders` pass; no `restricted` value in stdout, stderr, summary JSON or logs | proposed | — |
| TS-039 | MVP-14 | Governance guard fails on a forged manifest with `email` in a mart and passes on the real one | proposed | — |
| TS-040 | MVP-16 | `ANALYST` sees masked `investors` PII, `TRANSFORMER` clear values, also after a full run with `SWAP`; no `restricted` tag in `MARTS` | proposed | — |

A test only becomes `approved` with the user's explicit acceptance.

## Open items

- MVP backlog rows follow the approved critical path (ADR-0017): T-031 → T-032 → T-033 → T-034 → T-036 → T-045 → T-037 → T-038 → T-046 → T-035 → T-039 → T-040 → T-043 → T-044 → T-047 → T-048. T-041 and T-042 are deferred (C2).
- Columns outside the contract in the header (T-026): decided, reject with exit 2 (ADR-0017, C5); implemented in MVP-04 (T-034).
- Acceptance of the F0.1 tests after review.
