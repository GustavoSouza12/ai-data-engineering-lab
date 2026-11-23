# Phase 0 transformation (`orders`, F0.2a)

dbt-core with dbt-duckdb, local only. The single target is `dev`, a DuckDB file
(`transform/lab_dev.duckdb`, ignored by git). `profiles.yml` holds no secret: DuckDB
needs none. The Snowflake target arrives in a later MVP item.

## Run end to end

From the repository root:

```
scripts/run_local_pipeline.sh
```

It runs `uv sync --locked`, the generator, the validator (into `data/staging/orders/` and
`data/quarantine/orders/`) and `dbt build`, and stops at the first step that fails. On the
sample, `dbt build` exits 0 with 3 warnings (see "Semantic tests" below).

To run only dbt (after the validator):

```
cd transform
uv run dbt build --profiles-dir .
```

`LAB_DUCKDB_PATH` overrides the DuckDB file and the `orders_staging_dir` var overrides the
folder of validated CSVs. Both are relative to the directory dbt runs from.

## Lineage

```
data/staging/orders/*.csv (source orders_staging.orders, every column as text)
  -> stg_orders            view   trim (like Python str.strip), then drop exact duplicates, then cast
  |-> dq_orders_cross_file_conflicts table  every occurrence of a version key with different content across files
  -> int_orders__latest    view   one row per order_id, latest updated_at, without conflicted orders (ADR-0009)
  -> fct_orders            table  + rate_to_usd and amount_usd at the submitted_at date (ADR-0013)
  -> org_summary           view   marts/internal, one row per organization (seed), USD only
seeds: organizations (ORG-001 to ORG-020), fx_rates (2026-11-01 to 2026-11-12, USD/EUR/BRL)
```

The source reads every `*.csv` in the staging folder, so validated files of several days
are combined. Copies of the same version in different files are exact duplicates
(compared on the contract columns, after trimming) and only the first load is kept.

On the sample: 272 validated rows -> 270 in `stg_orders` -> 190 in `int_orders__latest` and
`fct_orders` -> 20 organizations in `org_summary` (ORG-016 to ORG-020 with zeros);
`dq_orders_cross_file_conflicts` is empty.

### Cross-file version conflicts (ADR-0009, amendment 2026-11-23)

Ingestion quarantines a conflict inside one file but sees one file at a time. dbt catches
the same version key (`order_id`, `updated_at`) with different content in different daily
files: every occurrence goes to `dq_orders_cross_file_conflicts` with its `_source_file`
and `reject_reason = conflicting_version_cross_file`, and the whole order is left out of
`int_orders__latest`, `fct_orders` and `org_summary`. No occurrence is picked as the winner
(never by `_loaded_at` or file position), and an older version is not published as the
current one. The other orders publish normally.

## Tests

| ID | Test | Severity |
|---|---|---|
| TS-008 | `fct_orders.order_id` `unique` and `not_null` | error |
| TS-009 | `channel`, `currency`, `status` within accepted values (`accepted_values_by_row`) | T3 |
| TS-010 | `amount` castable and > 0 | T3 |
| TS-011 | `assert_orders_reconcile_latest_to_gold`: count and `amount` sum per currency, `int_orders__latest` x `fct_orders` | error |
| TS-012 | `submitted_at <= updated_at` and `updated_at` date <= date in the file name | T3 |
| TS-019 | `int_orders__latest.order_id` unique and not null; `assert_int_orders__latest_is_latest_version` (latest version of every order without a cross-file conflict, no conflicted order) | error |
| TS-020 | `fct_orders.organization_id` -> `organizations`; `assert_every_order_has_fx_rate` | error |
| TS-021 | `org_summary.organization_id` unique and not null; `assert_org_summary_reconciles_with_gold` (20 organizations, totals = gold) | error |
| TS-026 | `assert_no_cross_file_conflicting_versions` (ADR-0009 amendment): one row per order in `dq_orders_cross_file_conflicts` | T3, threshold `cross_file_conflict_error_threshold` |

The cross-file conflict test follows T3: it warns from the first conflicted order and
errors only above `cross_file_conflict_error_threshold` conflicted orders (var, default 10:
one conflicted order never trips it; more than 10 in one build means the source's
versioning is broken). Its failures are stored like the others. `cross_file_conflict_severity`
stays `error`, because dbt applies `error_if` only at severity `error`.

Seeds are tested too (keys, accepted values, `rate_to_usd > 0`).

### Semantic tests (ADR-0017, T3)

The three planted semantic errors stay in gold. Their tests warn from the first failing row
and only error above `semantic_error_threshold` failing rows (var, default 10). Every test
stores its failures (`store_failures`) in the `main_dbt_test__audit` schema. On the sample:

| Test | Order |
|---|---|
| `ts009_fct_orders_channel_accepted` | `ORD-00047` (`channel = fax`) |
| `ts010_fct_orders_amount_castable_and_positive` | `ORD-00123` (negative `amount`) |
| `ts012_fct_orders_timestamps_within_file_date` | `ORD-00084` (`updated_at` after the file date) |

### Integration tests

```
uv run pytest transform/integration_tests -v
```

They cover TS-025 and TS-026. They run the validator and `dbt build` into a temporary directory (nothing is written to the
repository) and check the counts above, the stored failures, `amount_usd`, the governance
metadata and, with the two-file fixture in `integration_tests/fixtures/cross_file_conflict/`,
that a conflict across daily files warns, sends both occurrences to
`dq_orders_cross_file_conflicts`, leaves that order out of gold and publishes the others,
and that it fails the build when the threshold is set to 0.

## Governance

- Every column of models, seeds and the source has `meta.pii_level`; `amount` and the USD
  amounts are `confidential`, the rest `internal`.
- Every model and seed has a description and `meta.owner`.
- Never sum `amount` across currencies: use `amount_usd` or group by `currency` (ADR-0013).
- Stored failures keep whole rows, including `amount` (`confidential`); they live only in the
  local DuckDB file.
