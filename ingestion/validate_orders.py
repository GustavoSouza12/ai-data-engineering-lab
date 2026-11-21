"""Structural validation of ``orders`` (phase 0, ADR-0002 and ADR-0009).

Structural rules only:
- the header must contain every contract column, exactly once, and nothing else: a
  missing, duplicated, reserved (``_source_file``, ``_loaded_at``, ``reject_reason``) or
  off-contract column means exit code 2 and nothing written (ADR-0017, C5: a column
  without a ``pii_level`` never enters staging);
- required field empty or whitespace only -> quarantine with ``missing_<column>``;
- same (``order_id``, ``updated_at``) with different content -> every
  occurrence goes to quarantine with ``conflicting_version``;
- row with more fields than the header -> quarantine with ``extra_fields:<n>``
  (the extra fields are not written).

Versions (same ``order_id``, different ``updated_at``) and exact duplicates
go to staging: deduplicating and picking the latest version is the job of dbt
(F0.2). Types, accepted values and ``amount > 0`` are also left to dbt.

Usage:
    uv run python -m ingestion.validate_orders --input <raw.csv> --run-ts <ISO 8601 with timezone> \
        [--summary-json <path>]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
import traceback
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# Orders contract (ADR-0009). Single source: the generator imports it from here.
REQUIRED_COLUMNS: tuple[str, ...] = (
    "order_id",
    "organization_id",
    "investor_id",
    "fund_id",
    "amount",
    "currency",
    "channel",
    "status",
    "submitted_at",
    "updated_at",
)
VERSION_KEY: tuple[str, str] = ("order_id", "updated_at")
METADATA_COLUMNS: tuple[str, ...] = ("_source_file", "_loaded_at")
REJECT_REASON_COLUMN = "reject_reason"
# Names the validator adds to the outputs: an input column with one of them is rejected.
RESERVED_COLUMNS: tuple[str, ...] = METADATA_COLUMNS + (REJECT_REASON_COLUMN,)
REASON_SEPARATOR = ";"
CONFLICT_REASON = "conflicting_version"
EXTRA_FIELDS_REASON = "extra_fields"
EXTRA_FIELDS_COUNT_SEPARATOR = ":"
# csv.DictReader stores the extra fields of a row under this key (restkey).
EXTRA_FIELDS_KEY = None
LOADED_AT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

DEFAULT_STAGING_DIR = Path("data/staging/orders")
DEFAULT_QUARANTINE_DIR = Path("data/quarantine/orders")

EXIT_OK = 0
EXIT_RECONCILIATION_FAILED = 1
EXIT_INVALID_INPUT = 2
EXIT_UNEXPECTED_ERROR = 3

Row = dict  # dict[str | None, str | list[str]]: the None key exists only with extra fields


class InvalidInputError(Exception):
    """Invalid input: the validator exits with code 2 without writing anything."""


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def missing_header_columns(fieldnames: Iterable[str] | None) -> list[str]:
    """Required columns missing from the header, in contract order."""
    present = set(fieldnames or [])
    return [col for col in REQUIRED_COLUMNS if col not in present]


def header_error(fieldnames: Iterable[str] | None) -> str | None:
    """Why the header is rejected (exit code 2), or None if it is valid.

    Checked in this order: missing contract columns, reserved names, off-contract
    columns, duplicated columns. The message names only contract or reserved
    columns; off-contract columns are reported by 1-based position, because their
    names come from the file and are not under the contract.
    """
    names = list(fieldnames or [])
    missing = missing_header_columns(names)
    if missing:
        return "header is missing required column(s): " + ", ".join(missing)
    reserved = sorted({n for n in names if n in RESERVED_COLUMNS}, key=RESERVED_COLUMNS.index)
    if reserved:
        return "header uses reserved column name(s): " + ", ".join(reserved)
    off_contract = [str(i) for i, n in enumerate(names, start=1) if n not in REQUIRED_COLUMNS]
    if off_contract:
        return (
            "header has column(s) outside the contract at position(s): "
            + ", ".join(off_contract)
        )
    counts = Counter(names)
    duplicated = [col for col in REQUIRED_COLUMNS if counts[col] > 1]
    if duplicated:
        return "header has duplicated column(s): " + ", ".join(duplicated)
    return None


def normalize_run_ts(run_ts: str) -> str:
    """Convert ``--run-ts`` to UTC in the ``YYYY-MM-DDTHH:MM:SSZ`` format.

    Requires an explicit timezone (``Z`` or an offset): a naive timestamp is
    ambiguous and would break idempotent reruns on machines in different
    timezones. Fractional seconds are dropped.

    Error messages never echo the received value.
    """
    try:
        parsed = datetime.fromisoformat(run_ts)
    except ValueError:
        raise InvalidInputError("--run-ts is not a valid ISO 8601 timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InvalidInputError(
            "--run-ts has no timezone; use Z or an offset (e.g. 2026-01-01T00:00:00Z)"
        )
    return parsed.astimezone(timezone.utc).strftime(LOADED_AT_FORMAT)


def _same_dir(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def check_output_dirs(
    input_path: Path,
    staging_dir: Path,
    quarantine_dir: Path,
    summary_json: Path | None = None,
) -> None:
    """Reject output directories that collide with each other or with the raw directory.

    Staging and quarantine reuse the input file name: in the same directory
    one would overwrite the other; in the raw directory they would overwrite
    the input itself.
    """
    input_dir = input_path.parent
    if _same_dir(staging_dir, quarantine_dir):
        raise InvalidInputError("--staging-dir and --quarantine-dir cannot be the same directory")
    if _same_dir(staging_dir, input_dir):
        raise InvalidInputError("--staging-dir cannot be the directory of the input file")
    if _same_dir(quarantine_dir, input_dir):
        raise InvalidInputError("--quarantine-dir cannot be the directory of the input file")
    if summary_json is not None:
        # The raw directory is versioned (ADR-0005): no report is written into it.
        if _same_dir(summary_json.parent, input_dir):
            raise InvalidInputError("--summary-json cannot be in the directory of the input file")
        for taken in (staging_dir / input_path.name, quarantine_dir / input_path.name):
            if _same_dir(summary_json, taken):
                raise InvalidInputError("--summary-json cannot be one of the CSV outputs")
        if summary_json.is_dir():
            raise InvalidInputError("--summary-json is a directory")


def _is_blank(value: object) -> bool:
    return value is None or not isinstance(value, str) or value.strip() == ""


def _content(row: Row) -> tuple[str, ...]:
    """Contract values with surrounding whitespace stripped (basis for comparisons)."""
    return tuple((row.get(col) or "").strip() for col in REQUIRED_COLUMNS)


def _version_key(row: Row) -> tuple[str, str] | None:
    """Stripped (``order_id``, ``updated_at``); None if either part is blank.

    Blank keys are excluded from conflict detection: they are already ``missing_<column>``.
    """
    values = [row.get(col) for col in VERSION_KEY]
    if any(_is_blank(v) for v in values):
        return None
    return (values[0].strip(), values[1].strip())


def find_conflicting_keys(rows: Iterable[Row]) -> set[tuple[str, str]]:
    """Version keys that appear with more than one distinct content."""
    contents: dict[tuple[str, str], set[tuple[str, ...]]] = defaultdict(set)
    for row in rows:
        key = _version_key(row)
        if key is not None:
            contents[key].add(_content(row))
    return {key for key, variants in contents.items() if len(variants) > 1}


def extra_field_count(row: Row) -> int:
    extras = row.get(EXTRA_FIELDS_KEY)
    return len(extras) if extras else 0


def row_reasons(row: Row, conflicting_keys: set[tuple[str, str]]) -> list[str]:
    """Reject reasons for a row, in a stable order.

    ``missing_<column>`` in contract order, then ``conflicting_version``,
    then ``extra_fields:<n>``.
    """
    reasons = [f"missing_{col}" for col in REQUIRED_COLUMNS if _is_blank(row.get(col))]
    if _version_key(row) in conflicting_keys:
        reasons.append(CONFLICT_REASON)
    n_extra = extra_field_count(row)
    if n_extra:
        reasons.append(f"{EXTRA_FIELDS_REASON}{EXTRA_FIELDS_COUNT_SEPARATOR}{n_extra}")
    return reasons


def split_rows(
    rows: list[Row], source_file: str, loaded_at: str
) -> tuple[list[Row], list[Row]]:
    """Split rows into staging and quarantine, preserving the original order.

    Adds ``_source_file`` and ``_loaded_at`` to every row; quarantine rows also
    get ``reject_reason``. Extra fields are not copied.
    """
    conflicting_keys = find_conflicting_keys(rows)
    staging: list[Row] = []
    quarantine: list[Row] = []
    for row in rows:
        enriched = {k: v for k, v in row.items() if k is not EXTRA_FIELDS_KEY}
        enriched.update({"_source_file": source_file, "_loaded_at": loaded_at})
        reasons = row_reasons(row, conflicting_keys)
        if reasons:
            enriched[REJECT_REASON_COLUMN] = REASON_SEPARATOR.join(reasons)
            quarantine.append(enriched)
        else:
            staging.append(enriched)
    return staging, quarantine


def reason_code(reason: str) -> str:
    """``extra_fields:2`` -> ``extra_fields``; other reasons are unchanged."""
    return reason.split(EXTRA_FIELDS_COUNT_SEPARATOR, 1)[0]


def reason_counts(quarantine: Iterable[Row]) -> dict[str, int]:
    """Count per reason code (a row with two reasons counts toward both)."""
    counts: Counter[str] = Counter()
    for row in quarantine:
        counts.update(reason_code(r) for r in row[REJECT_REASON_COLUMN].split(REASON_SEPARATOR))
    return dict(sorted(counts.items()))


def count_exact_duplicates(rows: Iterable[Row]) -> int:
    """Rows whose contract content repeats an earlier row (informational)."""
    counts = Counter(_content(row) for row in rows)
    return sum(n - 1 for n in counts.values())


def count_versioned_orders(rows: Iterable[Row]) -> int:
    """``order_id`` values with more than one distinct ``updated_at`` (informational)."""
    versions: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        key = _version_key(row)
        if key is not None:
            versions[key[0]].add(key[1])
    return sum(1 for updated in versions.values() if len(updated) > 1)


def reconcile(n_input: int, n_staging: int, n_quarantine: int) -> bool:
    """Input = staging + quarantine."""
    return n_input == n_staging + n_quarantine


@dataclass
class Summary:
    input_rows: int
    staging_rows: int
    quarantine_rows: int
    reasons: dict[str, int] = field(default_factory=dict)
    exact_duplicates: int = 0
    versioned_orders: int = 0

    @property
    def reconciled(self) -> bool:
        return reconcile(self.input_rows, self.staging_rows, self.quarantine_rows)

    def render(self) -> str:
        lines = [
            f"input:      {self.input_rows}",
            f"staging:    {self.staging_rows}",
            f"  exact duplicates (dbt deduplicates): {self.exact_duplicates}",
            f"  order_id with more than one version (dbt picks the latest): {self.versioned_orders}",
            f"quarantine: {self.quarantine_rows}",
        ]
        for reason, n in self.reasons.items():
            lines.append(f"  {reason}: {n}")
        status = "OK" if self.reconciled else "FAILED"
        lines.append(
            f"reconciliation: {status} "
            f"({self.input_rows} = {self.staging_rows} + {self.quarantine_rows})"
        )
        return "\n".join(lines)

    def to_json_dict(self, source_file: str) -> dict:
        """Counts and reason codes only: never row content (G-1/G-2).

        ``source_file`` is the input file name (never a path).
        """
        return {
            "source_file": source_file,
            "input_rows": self.input_rows,
            "staging_rows": self.staging_rows,
            "quarantine_rows": self.quarantine_rows,
            "reasons": dict(self.reasons),
            "exact_duplicates": self.exact_duplicates,
            "versioned_orders": self.versioned_orders,
            "reconciled": self.reconciled,
        }


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def read_csv(path: Path) -> tuple[list[str] | None, list[Row]]:
    """Read the whole CSV into memory.

    Non-UTF-8 bytes or an unreadable CSV become ``InvalidInputError`` (exit code 2).
    The message carries only the file name and the position, never the row content.
    """
    reader = None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh, restkey=EXTRA_FIELDS_KEY)
            rows = list(reader)
            return reader.fieldnames, rows
    except UnicodeDecodeError as exc:
        raise InvalidInputError(
            f"{path.name} is not valid UTF-8 (invalid byte at position {exc.start})"
        ) from None
    except csv.Error:
        line = reader.line_num if reader is not None else 0
        raise InvalidInputError(f"{path.name} is not a readable CSV (line {line})") from None


def _new_temp(directory: Path, name: str, temps: list[Path]) -> Path:
    """Create the temp file in the target directory and register it before writing.

    This way the ``finally`` in ``run`` deletes the file even if the write fails.
    """
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=directory)
    os.close(fd)
    path = Path(tmp)
    temps.append(path)
    return path


def _write_csv(path: Path, fieldnames: list[str], rows: list[Row]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def count_data_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return sum(1 for _ in csv.DictReader(fh))


def run(
    input_path: Path,
    run_ts: str,
    staging_dir: Path = DEFAULT_STAGING_DIR,
    quarantine_dir: Path = DEFAULT_QUARANTINE_DIR,
    summary_json: Path | None = None,
) -> int:
    """Run the validation and return the exit code (0, 1 or 2).

    With ``summary_json``, the summary is also written there as JSON, only when the
    run succeeds (exit code 0) and after the CSV outputs are published.

    Unexpected exceptions propagate; ``main`` turns them into exit code 3.
    """
    try:
        loaded_at = normalize_run_ts(run_ts)
        if not input_path.is_file():
            raise InvalidInputError(f"input file not found: {input_path.name}")
        check_output_dirs(input_path, staging_dir, quarantine_dir, summary_json)
        fieldnames, rows = read_csv(input_path)
        problem = header_error(fieldnames)
        if problem:
            raise InvalidInputError(problem)
    except InvalidInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT

    source_file = input_path.name
    staging, quarantine = split_rows(rows, source_file=source_file, loaded_at=loaded_at)

    staging_fields = list(fieldnames) + list(METADATA_COLUMNS)
    quarantine_fields = staging_fields + [REJECT_REASON_COLUMN]

    temps: list[Path] = []
    try:
        tmp_staging = _new_temp(staging_dir, source_file, temps)
        _write_csv(tmp_staging, staging_fields, staging)
        tmp_quarantine = _new_temp(quarantine_dir, source_file, temps)
        _write_csv(tmp_quarantine, quarantine_fields, quarantine)

        # Reconcile what was actually written, before publishing.
        summary = Summary(
            input_rows=len(rows),
            staging_rows=count_data_rows(tmp_staging),
            quarantine_rows=count_data_rows(tmp_quarantine),
            reasons=reason_counts(quarantine),
            exact_duplicates=count_exact_duplicates(staging),
            versioned_orders=count_versioned_orders(staging),
        )
        print(summary.render())
        if not summary.reconciled:
            print("error: reconciliation failed; nothing published", file=sys.stderr)
            return EXIT_RECONCILIATION_FAILED

        tmp_summary = None
        if summary_json is not None:
            tmp_summary = _new_temp(summary_json.parent, summary_json.name, temps)
            _write_json(tmp_summary, summary.to_json_dict(source_file))

        os.replace(tmp_staging, staging_dir / source_file)
        os.replace(tmp_quarantine, quarantine_dir / source_file)
        if tmp_summary is not None:
            os.replace(tmp_summary, summary_json)
        temps.clear()
        return EXIT_OK
    finally:
        for tmp in temps:
            tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Structural validation of orders (phase 0).")
    parser.add_argument("--input", required=True, type=Path, help="Raw input CSV.")
    parser.add_argument(
        "--run-ts",
        required=True,
        help="ISO 8601 timestamp with timezone (Z or offset); becomes _loaded_at in UTC.",
    )
    parser.add_argument("--staging-dir", type=Path, default=DEFAULT_STAGING_DIR)
    parser.add_argument("--quarantine-dir", type=Path, default=DEFAULT_QUARANTINE_DIR)
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help=(
            "Also write the summary (counts and reason codes, no row content) as JSON to this "
            "path; written only on exit code 0. Input of ingestion.batch_guard."
        ),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help=(
            "Show the traceback of unexpected errors. Unsafe: may expose paths and values; "
            "never enable in a DAG/production."
        ),
    )
    args = parser.parse_args(argv)
    try:
        return run(
            args.input, args.run_ts, args.staging_dir, args.quarantine_dir, args.summary_json
        )
    except Exception as exc:  # noqa: BLE001 - entry point: becomes exit code 3
        # The exception text may contain data values or absolute paths:
        # outside --debug, print only the type.
        print(
            f"unexpected error ({type(exc).__name__}); run with --debug for details",
            file=sys.stderr,
        )
        if args.debug:
            traceback.print_exc()
        return EXIT_UNEXPECTED_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
