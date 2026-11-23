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
  -> int_orders__latest    view   one row per order_id, latest updated_at (ADR-0009)
  -> fct_orders            table  + rate_to_usd and amount_usd at the submitted_at date (ADR-0013)
  -> org_summary           view   marts/internal, one row per organization (seed), USD only
seeds: organizations (ORG-001 to ORG-020), fx_rates (2026-11-01 to 2026-12-31, USD/EUR/BRL)
```

The source reads every `*.csv` in the staging folder, so validated files of several days
are combined. Copies of the same version in different files are exact duplicates
(compared on the contract columns, after trimming) and only the first load is kept.

On the sample: 272 validated rows -> 270 in `stg_orders` -> 190 in `int_orders__latest` and
`fct_orders` -> 20 organizations in `org_summary` (ORG-016 to ORG-020 with zeros).

## Tests

| ID | Test | Severity |
|---|---|---|
| TS-008 | `fct_orders.order_id` `unique` and `not_null` | error |
| TS-009 | `channel`, `currency`, `status` within accepted values (`accepted_values_by_row`) | T3 |
| TS-010 | `amount` castable and > 0 | T3 |
| TS-011 | `assert_orders_reconcile_latest_to_gold`: count and `amount` sum per currency, `int_orders__latest` x `fct_orders` | error |
| TS-012 | `submitted_at <= updated_at` and `updated_at` date <= date in the file name | T3 |
| TS-019 | `int_orders__latest.order_id` unique and not null; `assert_int_orders__latest_is_latest_version` | error |
| TS-020 | `fct_orders.organization_id` -> `organizations`; `assert_every_order_has_fx_rate` | error |
| TS-021 | `org_summary.organization_id` unique and not null; `assert_org_summary_reconciles_with_gold` (20 organizations, totals = gold) | error |
| TS-026 | `assert_no_cross_file_conflicting_versions` (ADR-0009): same (`order_id`, `updated_at`), different content, across daily files | error (var `cross_file_conflict_severity`) |

The cross-file conflict test errors by default (ADR-0009: no silent resolution). How gold
should treat such a conflict is pending the owner's decision; until then the severity lives
only in the `cross_file_conflict_severity` var of `dbt_project.yml`, and there is no
exclusion or quarantine logic for it.

Seeds are tested too (keys, accepted values, `rate_to_usd > 0`).

`fx_rates` covers 2026-11-01 to 2026-12-31: the sample's dates plus every daily file date the
generator writes up to 2026-12-31. It is extended by `ingestion/generate_fx_rates.py` (see
`ingestion/README.md`); an order submitted after 2026-12-31 fails TS-020.

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
that a conflict across daily files fails the build.

`test_local_pipeline.py` runs the whole local chain on the sample plus the next two daily
files: generator -> validator `--summary-json` -> batch guard -> `dbt build --target dev`. It
expects exit 0, TS-020 passing for the daily files' new orders, and only the three T3
warnings plus the cross-file conflict test, which it lowers to `warn` because every daily
file plants one conflict (ADR-0009).

## Governance

- Every column of models, seeds and the source has `meta.pii_level`; `amount` and the USD
  amounts are `confidential`, the rest `internal`.
- Every model and seed has a description and `meta.owner`.
- Never sum `amount` across currencies: use `amount_usd` or group by `currency` (ADR-0013).
- Stored failures keep whole rows, including `amount` (`confidential`); they live only in the
  local DuckDB file.
