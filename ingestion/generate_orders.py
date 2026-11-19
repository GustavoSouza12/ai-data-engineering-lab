"""Generate a synthetic ``orders`` CSV with versions and planted errors (ADR-0009).

Standard library only and ``random.Random(42)``: the same run always
produces the same file. Every ID is fictitious (ADR-0002, ADR-0007).

Usage:
    uv run python -m ingestion.generate_orders --output data/raw/orders/orders_2026-11-19.csv
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

from ingestion.validate_orders import EXTRA_FIELDS_KEY, REQUIRED_COLUMNS

COLUMNS: tuple[str, ...] = REQUIRED_COLUMNS
CURRENCIES: tuple[str, ...] = ("USD", "EUR", "BRL")
CHANNELS: tuple[str, ...] = ("advisor", "direct", "platform")
STATUSES: tuple[str, ...] = (
    "submitted",
    "sponsor_review",
    "nigo",
    "approved",
    "signed",
    "completed",
    "cancelled",
)
# Status progressions for orders with more than one version.
PROGRESSIONS_2: tuple[tuple[str, ...], ...] = (
    ("submitted", "approved"),
    ("submitted", "cancelled"),
)
PROGRESSIONS_3: tuple[tuple[str, ...], ...] = (
    ("submitted", "approved", "completed"),
    ("submitted", "approved", "cancelled"),
)

SEED = 42
N_ORDERS = 200  # distinct orders
N_ORGANIZATIONS_WITH_ORDERS = 15  # ORG-001 to ORG-015; ORG-016 to ORG-020 have no orders
N_INVESTORS = 60
N_FUNDS = 25
N_ORDERS_2_VERSIONS = 40
N_ORDERS_3_VERSIONS = 20
N_VERSIONED_ORDERS = N_ORDERS_2_VERSIONS + N_ORDERS_3_VERSIONS
P_AMOUNT_CHANGE = 0.3  # chance that amount changes in a new version

FILE_DATE_END = datetime(2026, 11, 19, 23, 59, 59)  # end of the file date
_SUBMIT_START = datetime(2026, 11, 1)
_SUBMIT_WINDOW_SECONDS = 12 * 24 * 60 * 60  # submitted_at between Nov 1 and Nov 12
_MIN_STEP_SECONDS = 60 * 60  # at least 1 h between versions
_MAX_STEP_SECONDS = 48 * 60 * 60  # at most 48 h between versions

# Errors planted on purpose. Each one lands on a different row, always in
# single-version orders, so that the counts are exact.
# Structural (must go to quarantine):
N_EMPTY_FIELD = 4  # one required field empty
N_WHITESPACE_FIELD = 3  # one required field with whitespace only
N_CONFLICTS = 2  # pairs with the same (order_id, updated_at) and different content
N_EXTRA_FIELD = 1  # row with one field more than the header
# Legitimate repetition (goes to staging; dbt deduplicates in F0.2):
N_EXACT_DUPLICATES = 2  # identical copies of a row
# Semantic (structurally valid: they pass ingestion, dbt catches them in F0.2):
N_NEGATIVE_AMOUNT = 1
N_INVALID_CHANNEL = 1
N_FUTURE_UPDATED_AT = 1  # updated_at later than the file date

INVALID_CHANNEL = "fax"
WHITESPACE_VALUE = "   "
EXTRA_FIELD_VALUE = "unexpected"
FUTURE_UPDATED_AT = "2026-11-21T09:00:00"

N_BASE_ROWS = N_ORDERS + N_ORDERS_2_VERSIONS + 2 * N_ORDERS_3_VERSIONS
N_ROWS = N_BASE_ROWS + N_CONFLICTS + N_EXACT_DUPLICATES
EXPECTED_QUARANTINE_ROWS = (
    N_EMPTY_FIELD + N_WHITESPACE_FIELD + 2 * N_CONFLICTS + N_EXTRA_FIELD
)
EXPECTED_STAGING_ROWS = N_ROWS - EXPECTED_QUARANTINE_ROWS

Row = dict  # the EXTRA_FIELDS_KEY (None) key holds extra fields, as in csv.DictReader


def _fmt(ts: datetime) -> str:
    return ts.isoformat(timespec="seconds")


def _amount(rng: random.Random) -> str:
    cents = rng.randint(1_000_00, 500_000_00)
    return f"{cents // 100}.{cents % 100:02d}"


def _investor(rng: random.Random) -> str:
    return f"INV-{rng.randint(1, N_INVESTORS):04d}"


def _order_versions(rng: random.Random, order_number: int, n_versions: int) -> list[Row]:
    """Versions of one order, with strictly increasing ``updated_at``."""
    submitted = _SUBMIT_START + timedelta(seconds=rng.randrange(_SUBMIT_WINDOW_SECONDS))
    base = {
        "order_id": f"ORD-{order_number:05d}",
        "organization_id": f"ORG-{rng.randint(1, N_ORGANIZATIONS_WITH_ORDERS):03d}",
        "investor_id": _investor(rng),
        "fund_id": f"FND-{rng.randint(1, N_FUNDS):03d}",
        "amount": _amount(rng),
        "currency": rng.choice(CURRENCIES),
        "channel": rng.choice(CHANNELS),
        "submitted_at": _fmt(submitted),
    }
    if n_versions == 1:
        statuses: tuple[str, ...] = (rng.choice(STATUSES),)
    elif n_versions == 2:
        statuses = rng.choice(PROGRESSIONS_2)
    else:
        statuses = rng.choice(PROGRESSIONS_3)

    versions: list[Row] = []
    updated = submitted
    for i, status in enumerate(statuses):
        if i > 0:
            updated += timedelta(seconds=rng.randint(_MIN_STEP_SECONDS, _MAX_STEP_SECONDS))
            if rng.random() < P_AMOUNT_CHANGE:
                base = {**base, "amount": _amount(rng)}
        versions.append({**base, "status": status, "updated_at": _fmt(updated)})
    return versions


def _with_contract_order(row: Row) -> Row:
    ordered: Row = {col: row[col] for col in COLUMNS}
    if EXTRA_FIELDS_KEY in row:
        ordered[EXTRA_FIELDS_KEY] = row[EXTRA_FIELDS_KEY]
    return ordered


def generate_orders(seed: int = SEED) -> list[Row]:
    """Return ``N_ROWS`` synthetic rows with versions and planted errors."""
    rng = random.Random(seed)
    order_numbers = list(range(1, N_ORDERS + 1))
    n_versions = {n: 1 for n in order_numbers}
    versioned = rng.sample(order_numbers, N_VERSIONED_ORDERS)
    for n in versioned[:N_ORDERS_2_VERSIONS]:
        n_versions[n] = 2
    for n in versioned[N_ORDERS_2_VERSIONS:]:
        n_versions[n] = 3

    rows: list[Row] = []
    for n in order_numbers:
        rows.extend(_order_versions(rng, n, n_versions[n]))
    # Order of an incremental extract: by updated_at, then order_id.
    rows.sort(key=lambda r: (r["updated_at"], r["order_id"]))

    # Each planted error uses a distinct row of a single-version order.
    single = [i for i, r in enumerate(rows) if n_versions[int(r["order_id"][4:])] == 1]
    n_planted = (
        N_CONFLICTS
        + N_EXACT_DUPLICATES
        + N_EMPTY_FIELD
        + N_WHITESPACE_FIELD
        + N_EXTRA_FIELD
        + N_NEGATIVE_AMOUNT
        + N_INVALID_CHANNEL
        + N_FUTURE_UPDATED_AT
    )
    picked = iter(rng.sample(single, n_planted))

    def take(n: int) -> list[int]:
        return [next(picked) for _ in range(n)]

    conflict_idx = take(N_CONFLICTS)
    duplicate_idx = take(N_EXACT_DUPLICATES)
    for i in take(N_EMPTY_FIELD):
        rows[i][rng.choice(COLUMNS)] = ""
    for i in take(N_WHITESPACE_FIELD):
        rows[i][rng.choice(COLUMNS)] = WHITESPACE_VALUE
    for i in take(N_EXTRA_FIELD):
        rows[i][EXTRA_FIELDS_KEY] = [EXTRA_FIELD_VALUE]
    for i in take(N_NEGATIVE_AMOUNT):
        rows[i]["amount"] = "-" + rows[i]["amount"]
    for i in take(N_INVALID_CHANNEL):
        rows[i]["channel"] = INVALID_CHANNEL
    for i in take(N_FUTURE_UPDATED_AT):
        rows[i]["updated_at"] = FUTURE_UPDATED_AT

    # Copies created after the mutations, from the untouched original rows.
    extra_rows: list[Row] = []
    for i in conflict_idx:
        # Same (order_id, updated_at), different investor and amount (case ORD-00117).
        copy = dict(rows[i])
        while copy["investor_id"] == rows[i]["investor_id"]:
            copy["investor_id"] = _investor(rng)
        copy["amount"] = _amount(rng)
        extra_rows.append(copy)
    for i in duplicate_idx:
        extra_rows.append(dict(rows[i]))
    for copy in extra_rows:
        rows.insert(rng.randrange(len(rows) + 1), copy)

    assert len(rows) == N_ROWS
    return [_with_contract_order(r) for r in rows]


def write_csv(rows: list[Row], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow([row[c] for c in COLUMNS] + list(row.get(EXTRA_FIELDS_KEY, [])))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic orders (phase 0).")
    parser.add_argument("--output", required=True, type=Path, help="Path of the raw CSV.")
    parser.add_argument("--seed", type=int, default=SEED, help="Generator seed (default 42).")
    args = parser.parse_args(argv)
    rows = generate_orders(args.seed)
    write_csv(rows, args.output)
    print(f"{len(rows)} rows written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
