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

The validator requires all of them to be in the header, but not in this order: the outputs
keep the column order of the input file.

The key of a version is (`order_id`, `updated_at`). Ingestion adds `_source_file`
(file name) and `_loaded_at` (UTC, `YYYY-MM-DDTHH:MM:SSZ`).

## Generate the synthetic raw file

Deterministic (`random.Random(42)`, standard library only): the same run produces the same file.

```
uv run python -m ingestion.generate_orders --output data/raw/orders/orders_2026-11-19.csv
```

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
- `--debug` prints the traceback of unexpected errors. Unsafe: may expose paths and values;
  never enable in a DAG/production.

Rules (structural only; types and values are left to dbt):

- header missing any contract column -> exit code 2, nothing written;
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
| `2` | invalid input: incomplete header, missing file, bytes that are not UTF-8, unreadable CSV (for example, a field above `csv.field_size_limit()`), invalid `--run-ts` or one without a timezone, invalid directory flags |
| `3` | unexpected error (stderr shows only the exception type; text and traceback only with `--debug`) |

With code 2 nothing is written: the whole file is read before any output is created, so
there is no partial summary nor orphan `.tmp`, and previous outputs stay intact.

### What the messages show

- Files appear only by name (`orders_2026-11-19.csv`), never by absolute path:
  the path reveals the user name and the machine layout.
- Read errors report a position (byte or line), not the row content.
- `--run-ts` errors say what is wrong with the value but never echo it.
- Outside `--debug`, an unexpected error does not print the exception text, which may
  contain data values or paths. `--debug` prints the full traceback and therefore may show
  paths and values: use it only locally, with synthetic data, never in a DAG or production.

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
