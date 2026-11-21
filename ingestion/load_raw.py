"""Load the validator outputs into the local DuckDB ``RAW`` layer (MVP-06, ADR-0017).

Mirrors what ``COPY INTO`` will do in Snowflake ``RAW`` (MVP-15a), locally:

- the staging CSV of a daily file goes to ``raw.orders`` and its quarantine CSV to
  ``raw.orders_quarantine``;
- every column is text, exactly as the validator wrote it: the contract columns, then
  ``_source_file`` and ``_loaded_at`` (and ``reject_reason`` in the quarantine);
- idempotent per ``_source_file``: both targets are replaced (``DELETE`` + ``INSERT``) in
  one transaction, so a rerun gives the same counts and other days are untouched;
- reconciliation inside the transaction: rows in each file = rows in its target for that
  ``_source_file``; on a mismatch everything is rolled back and the exit code is 1.

Only file names, table names and counts are printed, never row values (G-1/G-2).

Usage:
    uv run python -m ingestion.load_raw --source-file orders_2026-11-19.csv \
        [--staging-dir data/staging/orders] [--quarantine-dir data/quarantine/orders] \
        [--database transform/lab_dev.duckdb]

Exit codes:
    0  loaded and reconciled
    1  reconciliation failed: rolled back, RAW unchanged
    2  invalid input: bad file name, missing file, unexpected header, row shape or
       ``_source_file``, or a RAW table whose columns differ from the contract
    3  unexpected error (only the exception type is printed); rolled back
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import duckdb

from ingestion.validate_orders import (
    DEFAULT_QUARANTINE_DIR,
    DEFAULT_STAGING_DIR,
    METADATA_COLUMNS,
    REJECT_REASON_COLUMN,
    REQUIRED_COLUMNS,
)

RAW_SCHEMA = "raw"
ORDERS_TABLE = "orders"
QUARANTINE_TABLE = "orders_quarantine"
SOURCE_FILE_COLUMN = "_source_file"
ORDERS_COLUMNS: tuple[str, ...] = REQUIRED_COLUMNS + METADATA_COLUMNS
QUARANTINE_COLUMNS: tuple[str, ...] = ORDERS_COLUMNS + (REJECT_REASON_COLUMN,)
# The metadata columns identify the load: they can never be null.
NOT_NULL_COLUMNS: tuple[str, ...] = METADATA_COLUMNS + (REJECT_REASON_COLUMN,)

# Same file the dbt `dev` target uses (transform/profiles.yml), from the repository root.
DEFAULT_DATABASE = Path("transform/lab_dev.duckdb")

EXIT_OK = 0
EXIT_RECONCILIATION_FAILED = 1
EXIT_INVALID_INPUT = 2
EXIT_UNEXPECTED_ERROR = 3

# csv.DictReader stores the extra fields of a row under this key (restkey).
_EXTRA_FIELDS_KEY = None


class InvalidInputError(Exception):
    """Invalid input: the loader exits with code 2 without touching RAW."""


@dataclass(frozen=True)
class Target:
    table: str
    columns: tuple[str, ...]

    @property
    def qualified(self) -> str:
        return f"{RAW_SCHEMA}.{self.table}"


ORDERS = Target(ORDERS_TABLE, ORDERS_COLUMNS)
QUARANTINE = Target(QUARANTINE_TABLE, QUARANTINE_COLUMNS)


@dataclass(frozen=True)
class TargetResult:
    target: Target
    file_rows: int
    replaced_rows: int
    loaded_rows: int

    @property
    def reconciled(self) -> bool:
        return self.file_rows == self.loaded_rows


@dataclass(frozen=True)
class LoadResult:
    source_file: str
    targets: tuple[TargetResult, ...]

    @property
    def reconciled(self) -> bool:
        return all(t.reconciled for t in self.targets)

    def render(self) -> str:
        width = max(len(t.target.qualified) for t in self.targets) + 1
        lines = [f"source file: {self.source_file}"]
        for t in self.targets:
            lines.append(
                f"{t.target.qualified + ':':<{width}} {t.loaded_rows} loaded "
                f"(file {t.file_rows}, replaced {t.replaced_rows})"
            )
        status = "OK" if self.reconciled else "FAILED"
        detail = "; ".join(
            f"file {t.file_rows} = {t.target.qualified} {t.loaded_rows}" for t in self.targets
        )
        lines.append(f"reconciliation: {status} ({detail})")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def check_source_file(name: str) -> str:
    """The idempotency key: a bare ``.csv`` file name, never a path."""
    if not name or name != Path(name).name or name in (".", "..") or "\\" in name:
        raise InvalidInputError("--source-file must be a file name, not a path")
    if not name.endswith(".csv"):
        raise InvalidInputError("--source-file must be a .csv file name")
    return name


def create_table_sql(target: Target) -> str:
    columns = ",\n    ".join(
        f"{col} VARCHAR{' NOT NULL' if col in NOT_NULL_COLUMNS else ''}" for col in target.columns
    )
    return f"CREATE TABLE IF NOT EXISTS {target.qualified} (\n    {columns}\n)"


def insert_sql(target: Target) -> str:
    placeholders = ", ".join("?" for _ in target.columns)
    return f"INSERT INTO {target.qualified} ({', '.join(target.columns)}) VALUES ({placeholders})"


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def read_validated_csv(path: Path, target: Target, source_file: str) -> list[tuple[str, ...]]:
    """Rows of a validator output, as text tuples in the target column order.

    The header must have every target column exactly once and nothing else (any order),
    every row must have exactly as many fields as the header, and every ``_source_file``
    must be ``source_file``. Messages carry only the file name and a line number.
    """
    if not path.is_file():
        raise InvalidInputError(f"{target.table} input not found: {path.name}")
    reader = None
    try:
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh, restkey=_EXTRA_FIELDS_KEY)
            fieldnames = reader.fieldnames or []
            if sorted(fieldnames) != sorted(target.columns):
                raise InvalidInputError(
                    f"{path.name} does not have the columns of {target.qualified}"
                )
            rows: list[tuple[str, ...]] = []
            for row in reader:
                values = tuple(row.get(col) for col in target.columns)
                if _EXTRA_FIELDS_KEY in row or any(v is None for v in values):
                    raise InvalidInputError(
                        f"{path.name} line {reader.line_num}: wrong number of fields"
                    )
                if row[SOURCE_FILE_COLUMN] != source_file:
                    raise InvalidInputError(
                        f"{path.name} line {reader.line_num}: "
                        f"{SOURCE_FILE_COLUMN} is not {source_file}"
                    )
                rows.append(values)
            return rows
    except UnicodeDecodeError:
        raise InvalidInputError(f"{path.name} is not valid UTF-8") from None
    except csv.Error:
        line = reader.line_num if reader is not None else 0
        raise InvalidInputError(f"{path.name} is not a readable CSV (line {line})") from None


def _table_columns(con: duckdb.DuckDBPyConnection, target: Target) -> list[tuple[str, str]]:
    return con.execute(
        "select column_name, data_type from information_schema.columns"
        " where table_catalog = current_database() and table_schema = ? and table_name = ?"
        " order by ordinal_position",
        [RAW_SCHEMA, target.table],
    ).fetchall()


def ensure_tables(con: duckdb.DuckDBPyConnection) -> None:
    """Create the RAW schema and tables if needed; reject tables that drifted."""
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {RAW_SCHEMA}")
    for target in (ORDERS, QUARANTINE):
        con.execute(create_table_sql(target))
        expected = [(col, "VARCHAR") for col in target.columns]
        if _table_columns(con, target) != expected:
            raise InvalidInputError(f"{target.qualified} has columns that differ from the contract")


def _count(con: duckdb.DuckDBPyConnection, target: Target, source_file: str) -> int:
    return con.execute(
        f"SELECT count(*) FROM {target.qualified} WHERE {SOURCE_FILE_COLUMN} = ?", [source_file]
    ).fetchone()[0]


def _insert_rows(
    con: duckdb.DuckDBPyConnection, target: Target, rows: list[tuple[str, ...]]
) -> None:
    if rows:
        con.executemany(insert_sql(target), rows)


def load(
    con: duckdb.DuckDBPyConnection,
    source_file: str,
    orders_rows: list[tuple[str, ...]],
    quarantine_rows: list[tuple[str, ...]],
) -> LoadResult:
    """Replace ``source_file`` in both RAW tables in one transaction.

    Commits only when both targets reconcile; otherwise rolls back and returns the
    unreconciled result. Any exception also rolls back before it propagates, so RAW is
    never left partially loaded.
    """
    con.execute("BEGIN TRANSACTION")
    try:
        ensure_tables(con)
        results = []
        for target, rows in ((ORDERS, orders_rows), (QUARANTINE, quarantine_rows)):
            replaced = _count(con, target, source_file)
            con.execute(
                f"DELETE FROM {target.qualified} WHERE {SOURCE_FILE_COLUMN} = ?", [source_file]
            )
            _insert_rows(con, target, rows)
            results.append(
                TargetResult(target, len(rows), replaced, _count(con, target, source_file))
            )
        result = LoadResult(source_file, tuple(results))
        con.execute("COMMIT" if result.reconciled else "ROLLBACK")
        return result
    except BaseException:
        con.execute("ROLLBACK")
        raise


def run(
    source_file: str,
    staging_dir: Path = DEFAULT_STAGING_DIR,
    quarantine_dir: Path = DEFAULT_QUARANTINE_DIR,
    database: Path = DEFAULT_DATABASE,
) -> int:
    """Run the load and return the exit code (0, 1 or 2).

    Both files are read and checked before the database is opened. Unexpected
    exceptions propagate; ``main`` turns them into exit code 3.
    """
    try:
        source_file = check_source_file(source_file)
        orders_rows = read_validated_csv(staging_dir / source_file, ORDERS, source_file)
        quarantine_rows = read_validated_csv(
            quarantine_dir / source_file, QUARANTINE, source_file
        )
        database.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(database)) as con:
            result = load(con, source_file, orders_rows, quarantine_rows)
    except InvalidInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT
    print(result.render())
    if not result.reconciled:
        print("error: reconciliation failed; rolled back, RAW unchanged", file=sys.stderr)
        return EXIT_RECONCILIATION_FAILED
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load validated orders and their quarantine into the local DuckDB RAW."
    )
    parser.add_argument(
        "--source-file",
        required=True,
        help="File name of the daily file (the idempotency key), e.g. orders_2026-11-19.csv.",
    )
    parser.add_argument("--staging-dir", type=Path, default=DEFAULT_STAGING_DIR)
    parser.add_argument("--quarantine-dir", type=Path, default=DEFAULT_QUARANTINE_DIR)
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help=f"DuckDB file (default {DEFAULT_DATABASE}, the dbt dev target).",
    )
    args = parser.parse_args(argv)
    try:
        return run(args.source_file, args.staging_dir, args.quarantine_dir, args.database)
    except Exception as exc:  # noqa: BLE001 - entry point: becomes exit code 3
        # DuckDB messages may quote values or paths: print only the type.
        print(f"unexpected error ({type(exc).__name__}); RAW unchanged", file=sys.stderr)
        return EXIT_UNEXPECTED_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
