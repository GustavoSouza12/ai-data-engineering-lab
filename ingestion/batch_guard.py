"""Quarantine batch guard (ADR-0017, T4): stop the batch when too much was quarantined.

The validator stays permissive per row (its exit codes do not change): a bad row goes
to quarantine and the run succeeds. This guard is the separate "quarantine above the
limit -> stop" step of the DAG. It reads the summary written by
``validate_orders --summary-json`` and fails when
``quarantine_rows / input_rows`` is above the limit (default 10%).
A file with zero input rows passes. The comparison is exact (``fractions.Fraction``):
a limit of ``0.1`` means exactly 1/10, so a batch at the limit never fails on a binary
rounding error and one just above it never passes on one.

Usage:
    uv run python -m ingestion.batch_guard --summary-json <path> [--max-quarantine-ratio 0.10]

Exit codes:
    0  within the limit
    1  quarantine above the limit: stop the batch
    2  invalid input: missing or unreadable summary, invalid counts, invalid limit
    3  unexpected error
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

DEFAULT_MAX_QUARANTINE_RATIO = 0.10

EXIT_OK = 0
EXIT_LIMIT_EXCEEDED = 1
EXIT_INVALID_INPUT = 2
EXIT_UNEXPECTED_ERROR = 3

_COUNT_FIELDS = ("input_rows", "staging_rows", "quarantine_rows")


class InvalidInputError(Exception):
    """Invalid summary or limit: the guard exits with code 2."""


@dataclass(frozen=True)
class GuardResult:
    input_rows: int
    quarantine_rows: int
    max_ratio: Fraction

    @property
    def ratio(self) -> Fraction:
        """Exact share of input rows in quarantine; 0 for an empty file."""
        if self.input_rows == 0:
            return Fraction(0)
        return Fraction(self.quarantine_rows, self.input_rows)

    @property
    def passed(self) -> bool:
        """Fails only when the ratio is strictly above the limit (exact comparison)."""
        return self.ratio <= self.max_ratio

    def render(self) -> str:
        status = "OK" if self.passed else "FAILED"
        return (
            f"quarantine ratio: {self.quarantine_rows}/{self.input_rows} "
            f"= {float(self.ratio):.1%} (limit {float(self.max_ratio):.1%}): {status}"
        )


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def validate_max_ratio(max_ratio: float | Fraction) -> Fraction:
    """The limit as an exact fraction between 0 and 1.

    A float is read through its shortest decimal form (``repr``), so ``0.1`` becomes
    exactly 1/10 and not the nearest binary value.
    """
    if isinstance(max_ratio, bool) or not isinstance(max_ratio, (int, float, Fraction)):
        raise InvalidInputError("the quarantine limit must be a number")
    if isinstance(max_ratio, float):
        if not math.isfinite(max_ratio):
            raise InvalidInputError("the quarantine limit must be between 0 and 1")
        max_ratio = Fraction(repr(max_ratio))
    limit = Fraction(max_ratio)
    if not 0 <= limit <= 1:
        raise InvalidInputError("the quarantine limit must be between 0 and 1")
    return limit


def parse_max_ratio(text: str) -> Fraction:
    """Parse the CLI limit exactly (``"0.1"`` -> 1/10)."""
    try:
        limit = Fraction(text.strip())
    except (ValueError, ZeroDivisionError):
        raise InvalidInputError("the quarantine limit must be a number") from None
    return validate_max_ratio(limit)


def check_batch(
    input_rows: int,
    quarantine_rows: int,
    max_ratio: float | Fraction = DEFAULT_MAX_QUARANTINE_RATIO,
) -> GuardResult:
    """Compare the quarantine share of a batch with the limit."""
    max_ratio = validate_max_ratio(max_ratio)
    for name, value in (("input_rows", input_rows), ("quarantine_rows", quarantine_rows)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise InvalidInputError(f"{name} must be a non-negative integer")
    if quarantine_rows > input_rows:
        raise InvalidInputError("quarantine_rows cannot be greater than input_rows")
    return GuardResult(input_rows, quarantine_rows, max_ratio)


def check_summary(
    summary: object, max_ratio: float | Fraction = DEFAULT_MAX_QUARANTINE_RATIO
) -> GuardResult:
    """Check a summary produced by ``validate_orders --summary-json``."""
    if not isinstance(summary, dict):
        raise InvalidInputError("the summary is not a JSON object")
    for name in _COUNT_FIELDS:
        value = summary.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise InvalidInputError(f"the summary field {name} must be a non-negative integer")
    if summary.get("reconciled") is not True:
        raise InvalidInputError("the summary is not reconciled")
    if summary["input_rows"] != summary["staging_rows"] + summary["quarantine_rows"]:
        raise InvalidInputError("the summary counts do not reconcile")
    return check_batch(summary["input_rows"], summary["quarantine_rows"], max_ratio)


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def load_summary(path: Path) -> object:
    """Read the summary JSON. Messages carry only the file name."""
    if not path.is_file():
        raise InvalidInputError(f"summary file not found: {path.name}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise InvalidInputError(f"{path.name} is not valid JSON") from None


def run(
    summary_json: Path, max_ratio: float | Fraction | str = DEFAULT_MAX_QUARANTINE_RATIO
) -> int:
    """Return the exit code; a ``str`` limit (from the CLI) is parsed exactly."""
    try:
        if isinstance(max_ratio, str):
            max_ratio = parse_max_ratio(max_ratio)
        result = check_summary(load_summary(summary_json), max_ratio)
    except InvalidInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT
    print(result.render())
    if not result.passed:
        print("error: quarantine above the limit; stop the batch", file=sys.stderr)
        return EXIT_LIMIT_EXCEEDED
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Quarantine batch guard (ADR-0017, T4).")
    parser.add_argument(
        "--summary-json",
        required=True,
        type=Path,
        help="Summary written by ingestion.validate_orders --summary-json.",
    )
    parser.add_argument(
        "--max-quarantine-ratio",
        default=str(DEFAULT_MAX_QUARANTINE_RATIO),
        help=(
            "Highest accepted quarantine_rows / input_rows, between 0 and 1 "
            f"(default {DEFAULT_MAX_QUARANTINE_RATIO})."
        ),
    )
    args = parser.parse_args(argv)
    try:
        return run(args.summary_json, args.max_quarantine_ratio)
    except Exception as exc:  # noqa: BLE001 - entry point: becomes exit code 3
        print(f"unexpected error ({type(exc).__name__})", file=sys.stderr)
        return EXIT_UNEXPECTED_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
