# Phase 0 ingestion (`orders`)

100% synthetic data (ADR-0002, ADR-0007). Python 3.11 via `uv`.

## Set up the environment

```
uv sync
```

## Contract (ADR-0009)

Required columns (defined once in `validate_orders.REQUIRED_COLUMNS` and imported by the
generator, which writes them in this order):

`order_id, organization_id, investor_id, fund_id, amount, currency, channel, status, submitted_at, updated_at`

The validator requires each of them in the header exactly once, and nothing else, but not
in this order: the outputs keep the column order of the input file.

The key of a version is (`order_id`, `updated_at`). Ingestion adds `_source_file`
(file name) and `_loaded_at` (UTC, `YYYY-MM-DDTHH:MM:SSZ`).

## Generate the synthetic raw files

Standard library only, deterministic by logical date: the file of a date uses seed
`42 + days since 2026-11-19`, so the same date always produces the same bytes. The first
date, and the default, is `2026-11-19`: it reproduces the versioned sample byte for byte.

```
uv run python -m ingestion.generate_orders                                 # the sample
uv run python -m ingestion.generate_orders --date 2026-11-20 --days 3      # 3 daily files
uv run python -m ingestion.generate_orders --date 2026-11-20 --plant-cross-file-conflict
uv run python -m ingestion.generate_orders --output data/raw/orders/orders_2026-11-19.csv
```

Files are written as `orders_<date>.csv` under `--output-dir` (default `data/raw/orders`);
`--output` sets the exact path and works only with `--days 1`. A date before `2026-11-19`,
a malformed date or `--days` below 1 exits with code 2 and writes nothing. Each later file
is built on the days before it, so generating a date replays the chain from the sample.

### The sample (`2026-11-19`): a full extract

There are 200 distinct orders from `ORG-001` to `ORG-015` (`ORG-016` to `ORG-020` have no
orders, for the `LEFT JOIN` in F0.2). 40 orders have 2 versions and 20 have 3: `status`
progresses (`submitted` -> `approved` -> `completed` or `cancelled`), `updated_at` increases
and `amount` may change. Planted errors (constants in `generate_orders.py`), always in
single-version orders:

| Error | Count | Destination at ingestion |
|---|---|---|
| Required field empty | 4 | quarantine (`missing_<column>`) |
| Field with whitespace only | 3 | quarantine (`missing_<column>`) |
| Conflict: same (`order_id`, `updated_at`), different content | 2 pairs | quarantine (`conflicting_version`, all 4 rows) |
| One field more than the header | 1 | quarantine (`extra_fields:1`) |
| Exact duplicate | 2 | staging (dbt deduplicates) |
| Negative `amount` | 1 | staging (semantic, dbt in F0.2) |
| `channel = fax` | 1 | staging (semantic, dbt in F0.2) |
| `updated_at` after the file date | 1 | staging (semantic, dbt in F0.2) |

Total: 284 rows -> 272 in staging + 12 in quarantine.

### Daily files (from `2026-11-20`): incremental extracts

Every file of date D after the sample has exactly 26 rows (constants `N_DAILY_*`), all
structurally valid, so ingestion sends 26 to staging and 0 to quarantine. With
`--plant-cross-file-conflict` it has 27: one cross-file conflict more.

| Rows | Count | Content |
|---|---|---|
| New versions | 10 | open orders whose latest version is in the file of D-1; `updated_at` on day D, after the previous version; `status` advances (`NEXT_STATUSES`), `amount` may change |
| New orders | 15 | `ORD-<200 + 15 * (k - 1) + 1>` onwards, for the k-th day after the sample; one version, `submitted`, `submitted_at = updated_at` on day D |
| Late version | 1 | new version of an older open order with `updated_at` on day D-2: more than 1 day old, inside the 3-day lookback (ADR-0010) |
| Cross-file conflict | 1, only with `--plant-cross-file-conflict` | same (`order_id`, `updated_at`) as a row of the file of D-1, different `amount`; the validator works per file and does not see it; dbt sends every occurrence to `dq_orders_cross_file_conflicts`, leaves the order out of gold and warns (ADR-0009, amendment 2026-11-23) |

Without the flag, no daily file repeats a version key of an earlier file. The flag applies
to the whole chain, so the bytes of a date depend on the flag but never on how the command
is called; the sample (`2026-11-19`) is the same either way.

Daily files add no semantic errors (the 3 of the sample stay the only ones) and never touch
an order with a planted error or one already used for a cross-file conflict.

`.gitattributes` marks `data/raw/**` as `-text` so git does not touch line endings or
trailing whitespace in the sample.

## Validate

```
uv run python -m ingestion.validate_orders --input data/raw/orders/orders_2026-11-19.csv --run-ts 2026-11-19T03:00:00Z
```

- `--run-ts` is required, must carry a timezone (`Z` or an offset, for example `-05:00`) and
  becomes `_loaded_at` in UTC. Same input + same `--run-ts` = same output bytes.
- Outputs: `data/staging/orders/<name>.csv` and `data/quarantine/orders/<name>.csv`
  (with `reject_reason`). Optional: `--staging-dir` and `--quarantine-dir`; they cannot be
  the same directory nor the directory of the input file.
- `--summary-json <path>` (optional) also writes the summary as JSON, the input of the
  [batch guard](#batch-guard). It is written only on exit code 0, after the CSV outputs are
  published. It cannot be in the directory of the input file (the raw directory is
versioned, ADR-0005) nor be one of the CSV outputs; its parent directory is created if
needed.
- `--debug` prints the traceback of unexpected errors. Unsafe: may expose paths and values;
  never enable in a DAG/production.

Rules (structural only; types and values are left to dbt):

- header problems -> exit code 2, nothing written. Checked in this order:
  - a contract column is missing;
  - a column uses a reserved name (`_source_file`, `_loaded_at`, `reject_reason`), which
    would collide with the columns the validator adds;
  - a column is outside the contract (ADR-0017, C5): a column without a `pii_level` never
    enters staging, so the whole file is rejected. Leading or trailing spaces in a column
    name, or an empty name, also make it off-contract;
  - a contract column appears more than once;
- required field empty or whitespace only -> `missing_<column>`;
- same (`order_id`, `updated_at`) with different content in any contract column
  -> every occurrence gets `conflicting_version`;
- an incomplete row (empty required field) with the same key as a complete row is also a
  conflict, and **both** go to quarantine (ADR-0009, interpretation F1: there is no way to
  prove which one is right). The complete row gets `conflicting_version`; the incomplete one
  gets both reasons, `missing_<column>;conflicting_version`. This way each code counts a
  single fact: `conflicting_version` counts every row involved in a conflict and
  `missing_<column>` counts every row with that field empty. A blank key (`order_id` or
  `updated_at`) is excluded from conflict detection: it is only `missing_<column>`;
- more fields than the header -> `extra_fields:<n>` (the extra fields are not written);
- versions (same `order_id`, different `updated_at`) and exact duplicates go to staging.
  The summary reports how many there are; deduplicating and picking the latest version is
  the job of dbt (F0.2).

Comparisons use values with surrounding whitespace stripped; the output keeps the original
value. When a row has more than one reason, the order is: `missing_<column>` (contract
order), `conflicting_version`, `extra_fields:<n>`, separated by `;`.

Outputs are written to temp files in the target directory and only published with
`os.replace` after the reconciliation (input = staging + quarantine) checks what was written.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | success |
| `1` | reconciliation failed (nothing published) |
| `2` | invalid input: incomplete header, reserved, off-contract or duplicated header column, missing file, bytes that are not UTF-8, unreadable CSV (for example, a field above `csv.field_size_limit()`), invalid `--run-ts` or one without a timezone, invalid directory or `--summary-json` flags |
| `3` | unexpected error (stderr shows only the exception type; text and traceback only with `--debug`) |

With code 2 nothing is written: the whole file is read before any output is created, so
there is no partial summary nor orphan `.tmp`, and previous outputs stay intact.

### What the messages show

- Files appear only by name (`orders_2026-11-19.csv`), never by absolute path:
  the path reveals the user name and the machine layout.
- Read errors report a position (byte or line), not the row content.
- Off-contract header columns are reported by position (1-based), not by name: the name
  comes from the file. Missing, reserved and duplicated columns are named, since those
  names come from the contract.
- The summary JSON carries only the input file name, the counts and the reason codes,
  never row content:

  ```json
  {
    "exact_duplicates": 2,
    "input_rows": 284,
    "quarantine_rows": 12,
    "reasons": {
      "conflicting_version": 4,
      "extra_fields": 1,
      "missing_channel": 3,
      "missing_fund_id": 1,
      "missing_organization_id": 1,
      "missing_submitted_at": 1,
      "missing_updated_at": 1
    },
    "reconciled": true,
    "source_file": "orders_2026-11-19.csv",
    "staging_rows": 272,
    "versioned_orders": 60
  }
  ```
- `--run-ts` errors say what is wrong with the value but never echo it.
- Outside `--debug`, an unexpected error does not print the exception text, which may
  contain data values or paths. `--debug` prints the full traceback and therefore may show
  paths and values: use it only locally, with synthetic data, never in a DAG or production.

## Batch guard

The validator stays permissive per row: bad rows go to quarantine and its exit codes do
not change. `ingestion/batch_guard.py` is the separate "quarantine above the limit -> stop"
step (ADR-0017, T4). It reads the summary JSON and fails when
`quarantine_rows / input_rows` is above the limit, 10% by default (`--max-quarantine-ratio`,
between 0 and 1). A ratio exactly at the limit passes; a header-only file (0 rows) passes.
The comparison is exact (`fractions.Fraction`): `0.1` means exactly 1/10, so the boundary
does not depend on binary floating-point rounding.

```
uv run python -m ingestion.validate_orders --input data/raw/orders/orders_2026-11-19.csv \
    --run-ts 2026-11-19T03:00:00Z --summary-json data/reports/orders_2026-11-19.json
uv run python -m ingestion.batch_guard --summary-json data/reports/orders_2026-11-19.json
```

The sample passes: 12/284 = 4.2%. The decision itself is the pure function
`check_batch(input_rows, quarantine_rows, max_ratio)`.

| Code | Meaning |
|---|---|
| `0` | quarantine within the limit |
| `1` | quarantine above the limit: stop the batch |
| `2` | invalid input: missing summary, invalid JSON, counts that are missing, negative, not reconciled or inconsistent, limit outside 0 to 1 |
| `3` | unexpected error (stderr shows only the exception type) |

## Test

```
uv run pytest -v
```

## Known limitations

- **A2: publishing the pair is not atomic.** Staging and quarantine are published by two
  consecutive `os.replace` calls. If the process dies between them, staging has the new
  version and quarantine the previous one. Rerunning with the same `--run-ts` fixes it.
- **A8: fully empty lines are ignored.** `csv.DictReader` skips blank lines, so they do not
  count toward the input nor the quarantine.
- **T-026: the UTF-8 error position can be wrong above about 8 KB.** The position reported
  for a byte that is not UTF-8 is relative to the decoded chunk, not to the file, so it can
  be wrong for files larger than about 8 KB. Tracked as follow-up T-026.
