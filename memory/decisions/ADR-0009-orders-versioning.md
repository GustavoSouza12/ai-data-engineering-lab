# ADR-0009 — `orders` versioning

- Date: 2026-11-19
- Status: accepted (recommendation approved by the user); amended on 2026-11-23 (cross-file conflicts, see "Amendment")
- Supersedes: ADR-0003. Changes: ADR-0002 (contract)

## Context
In production, an order changes state and amount over time, and the source sends each change as a new row. ADR-0003 treated any repeated `order_id` as an error and sent everything to quarantine, which would discard legitimate versions. At the same time, the `ORD-00117` case (same ID, different investor and fund, nothing saying which one is right) is still a real conflict.

## Decision

### `orders` contract (replaces the ADR-0002 table)

| Column | Expected type | Required | `pii_level` |
|---|---|---|---|
| `order_id` | text | yes | internal |
| `organization_id` | synthetic text (`ORG-001`) | yes | internal |
| `investor_id` | synthetic text (`INV-0001`) | yes | internal |
| `fund_id` | synthetic text (`FND-001`) | yes | internal |
| `amount` | decimal > 0 | yes | confidential |
| `currency` | `USD`, `EUR`, `BRL` | yes | internal |
| `channel` | `advisor`, `direct`, `platform` | yes | internal |
| `status` | `submitted`, `sponsor_review`, `nigo`, `approved`, `signed`, `completed`, `cancelled` | yes | internal |
| `submitted_at` | ISO 8601 datetime | yes | internal |
| `updated_at` | ISO 8601 datetime of the version | yes | internal |

A version's key is (`order_id`, `updated_at`). RAW keeps every version.

### Three kinds of repetition

| Case | How to recognize it | Where it is handled | Result |
|---|---|---|---|
| Exact duplicate | All columns equal | dbt staging | Keep one row; count it in a metric |
| Version | Same `order_id`, different `updated_at` | dbt intermediate | `row_number() over (partition by order_id order by updated_at desc, _loaded_at desc) = 1` picks the current one; history stays in RAW |
| Conflict | Same (`order_id`, `updated_at`), different content | Python ingestion | Every occurrence goes to quarantine with `conflicting_version` |

Key comparisons use the value with leading and trailing whitespace removed (`strip`). The original value is preserved in the output.

### Approved interpretations (F0.1 review, 2026-11-19)
- **Incomplete row with the same key as a complete one** (finding F1): counts as a conflict, and **both** rows go to quarantine. Conservative posture, chosen by the user: there is no way to prove which row is the true one.
- **`strip` applies to key and content** (finding F3): rows that differ only by leading or trailing whitespace are exact duplicates. Requirement for F0.2: dbt staging applies `trim` before deduplicating, so ingestion and dbt agree.
- **`extra_fields:<n>` reason**: the number of extra fields goes in the reason itself; aggregations use the code before the `:`.

## Rejected alternatives
- Keep ADR-0003: discards legitimate versions and breaks metrics such as "latest version of each order".
- Resolve conflicts with `row_number` by file position: deterministic but arbitrary; it can silently drop a real order.

## Consequences
- The F0.1 validator changes: `duplicate_order_id` goes away and is replaced by `conflicting_version`.
- The generator now produces versions, exact duplicates and conflicts.
- Every order metric starts from the latest version (`int_orders__latest`), never from RAW directly.

## Amendment (2026-11-23): conflicts across daily files

### Context
Ingestion validates one file at a time, so it cannot see a conflict between two daily files: the same version key (`order_id`, `updated_at`) with different content in different files. The MVP-05 architecture review (finding S1) found that the daily generator planted one such conflict in every daily file, and that `int_orders__latest` (`order by updated_at desc, _loaded_at desc`) let the later-loaded file win silently, which is resolution by file position, rejected above. Options: (a) warn and keep the later-loaded row; (b) dbt quarantines the conflicted order; (c) the generator plants the conflict only on a fixed day or behind a flag.

### Decision (the user's, 2026-11-23)
- **Detection is in dbt.** A version key whose content differs across daily files is a conflict, the same rule as inside one file. `stg_orders` removes exact duplicates first (after `trim`), so any key still repeated there is a conflict.
- **The conflicted order leaves gold and goes to quarantine/DQ.** Every occurrence of the conflicting key goes to `dq_orders_cross_file_conflicts`, with its `_source_file` and `reject_reason = conflicting_version_cross_file`. The whole order is left out of `int_orders__latest`, and so of `fct_orders` and everything downstream, not only the conflicting version: dropping only that version would publish an older version as the current one, another silent resolution. No winner is ever picked by `_loaded_at` or file position.
- **One conflicted order never blocks publishing the others** (`architecture.md` 3.5: permissive with the individual record, conservative with the batch). The cross-file conflict test (TS-026) follows the T3 pattern (ADR-0017), per batch: it counts the conflicted orders with an occurrence in the newest daily file, with `warn` from the first one, `error_if` above `cross_file_conflict_error_threshold` of them (default 10), and `store_failures`. Many conflicted orders in one batch mean the source's versioning is broken, and then the build stops. The count is not cumulative: conflicts from earlier batches stay quarantined and out of gold but do not count again, so they never make every later build fail.
- **The generator plants it only on request** (option c for the generator): daily files have no cross-file conflict unless `--plant-cross-file-conflict` is passed; with it, every daily file repeats one version key of the previous file with a different `amount`.

### Rejected alternatives
- (a) Warn and keep the later-loaded row: resolution by file position.
- Fail the whole build on any conflict: one bad order would stop the publish of every other order.

### Consequences
- The "Conflict" row of the table above now has two places: Python ingestion inside one file (`conflicting_version`) and dbt across files (`conflicting_version_cross_file`). The "Version" row's `row_number` no longer breaks ties by `_loaded_at`: after conflicted orders are removed, the version key is unique.
- A conflicted order stays out of gold; how a source correction re-admits it is not defined yet (ADR-0011 `DQ_ISSUES` lifecycle). Its rows stay in `stg_orders` and RAW.
