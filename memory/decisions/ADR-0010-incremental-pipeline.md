# ADR-0010 — Incremental pipeline, late data, deletes and reruns

- Date: 2026-11-19
- Status: accepted as a design; implementation in phases 1 to 4

## Context
Production sources insert and update records. Reprocessing the whole history on every run does not scale in cost or time.

## Decision

| Topic | Decision |
|---|---|
| New and changed rows | Incremental ingestion on the source's `updated_at` cursor (Airbyte: *incremental append* or CDC). RAW is **append-only**: it keeps every version with `_loaded_at` and `_source_file` |
| Insert × update | Not distinguished at ingestion: everything is a version. The distinction happens in gold, with `incremental_strategy = merge` and `unique_key = order_id` |
| Late data | The incremental window filters on `_loaded_at` (when it arrived), not `updated_at` (when it changed), with a **3-day lookback**. An old version that arrives today still gets processed |
| Duplicates | ADR-0009 |
| Deletes | A soft delete from CDC becomes `_is_deleted = true` in gold (the row does not disappear). Hard deletes without CDC are caught by a weekly source × RAW key reconciliation |
| Failed run | WAP: nothing is published; the previous gold stays live |
| Safe rerun | Every run receives a `logical_date`; nothing uses `now()`. Rerunning the same date replaces that day's RAW partition (by `_source_file`) and the `merge` converges to the same result |
| Accumulated drift | Scheduled monthly `full refresh` into `GOLD_STAGING`, compared with the incremental gold before the `SWAP` |
| Slowly changing attributes | dbt `snapshots` (SCD type 2) for funds and KYC, as in section 6 of the architecture |

## Consequences
Incremental models need idempotency tests: running the same `logical_date` twice must produce the same gold.
