"""Generate synthetic ``orders`` CSVs by logical date (ADR-0009, ADR-0010).

Standard library only (ADR-0004). Every ID is fictitious (ADR-0002, ADR-0007).

The base date (2026-11-19) is the versioned sample: a full extract with versions
and planted errors, generated with ``random.Random(42)``. Every later date is a
daily incremental file built on the days before it, with seed ``42 + days since
the base date``: the same date always produces the same bytes.

Daily files carry no cross-file version conflict unless ``--plant-cross-file-conflict``
is passed (ADR-0009, amendment of 2026-11-23): then every daily file repeats one version
key of the previous file with a different ``amount``.

Usage:
    uv run python -m ingestion.generate_orders                      # the base sample
    uv run python -m ingestion.generate_orders --date 2026-11-20 --days 3
    uv run python -m ingestion.generate_orders --date 2026-11-20 --plant-cross-file-conflict
    uv run python -m ingestion.generate_orders --output data/raw/orders/orders_2026-11-19.csv
"""

from __future__ import annotations

import argparse
import csv
import random
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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
EXPECTED_QUARANTINE_ROWS = N_EMPTY_FIELD + N_WHITESPACE_FIELD + 2 * N_CONFLICTS + N_EXTRA_FIELD
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
    return _generate_base(seed)[0]


def _generate_base(seed: int) -> tuple[list[Row], set[str]]:
    """Rows of the base file and the order_ids that carry a planted error or copy."""
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
    picked_idx = rng.sample(single, n_planted)
    # Captured before the mutations: a planted empty field may be order_id itself.
    planted_ids = {rows[i]["order_id"] for i in picked_idx}
    picked = iter(picked_idx)

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
    return [_with_contract_order(r) for r in rows], planted_ids


# Daily incremental files (MVP-05). Every file after the base date has, exactly:
N_DAILY_UPDATES = 10  # new versions of orders whose latest version is in the previous file
N_DAILY_NEW_ORDERS = 15  # orders never seen before, one version each, status "submitted"
N_DAILY_LATE_VERSIONS = 1  # a new version whose updated_at is on day D-2 of a file dated D
N_DAILY_ROWS = N_DAILY_UPDATES + N_DAILY_NEW_ORDERS + N_DAILY_LATE_VERSIONS
# Only with --plant-cross-file-conflict: same (order_id, updated_at) as a previous-file row.
N_DAILY_CROSS_FILE_CONFLICTS = 1
N_DAILY_ROWS_WITH_CONFLICT = N_DAILY_ROWS + N_DAILY_CROSS_FILE_CONFLICTS
LATE_DAYS_BEFORE = 2  # more than 1 day before the file date, inside the 3-day lookback

BASE_DATE = date(2026, 11, 19)  # date of the versioned sample, generated with the base seed
assert FILE_DATE_END.date() == BASE_DATE
_DAY_SECONDS = 24 * 60 * 60
TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "cancelled"})
# Allowed next status of a new version, by current status.
NEXT_STATUSES: dict[str, tuple[str, ...]] = {
    "submitted": ("sponsor_review", "approved", "cancelled"),
    "sponsor_review": ("approved", "nigo"),
    "nigo": ("sponsor_review", "cancelled"),
    "approved": ("signed", "cancelled"),
    "signed": ("completed",),
}
assert set(NEXT_STATUSES) | TERMINAL_STATUSES == set(STATUSES)


def day_seed(file_date: date, seed: int = SEED) -> int:
    """Seed of the file of ``file_date``: the base seed plus the days since the base date."""
    return seed + (file_date - BASE_DATE).days


def first_order_number(file_date: date) -> int:
    """Number of the first new order of a daily file (orders of the base file are 1..200)."""
    return N_ORDERS + ((file_date - BASE_DATE).days - 1) * N_DAILY_NEW_ORDERS + 1


@dataclass
class _History:
    latest: dict[str, Row]  # latest version of every order that may still get versions
    frozen: set[str]  # orders never touched again (planted errors, cross-file conflicts)
    previous_rows: list[Row]  # rows of the previous file


def _sample_sorted(rng: random.Random, population: set[str], k: int, what: str) -> list[str]:
    if len(population) < k:
        raise RuntimeError(f"not enough candidate orders for {what}: {len(population)} < {k}")
    return rng.sample(sorted(population), k)


def _new_version(rng: random.Random, row: Row, updated: datetime) -> Row:
    if row["updated_at"] >= _fmt(updated):
        raise RuntimeError("a new version must have a later updated_at")
    new = {**row, "status": rng.choice(NEXT_STATUSES[row["status"]]), "updated_at": _fmt(updated)}
    if rng.random() < P_AMOUNT_CHANGE:
        new["amount"] = _amount(rng)
    return new


def _daily_rows(
    rng: random.Random, file_date: date, history: _History, plant_cross_file_conflict: bool
) -> list[Row]:
    """Rows of the incremental file of ``file_date``; updates ``history`` in place."""
    day_start = datetime.combine(file_date, datetime.min.time())

    def during(day: datetime) -> datetime:
        return day + timedelta(seconds=rng.randrange(_DAY_SECONDS))

    open_ids = {oid for oid, r in history.latest.items() if r["status"] not in TERMINAL_STATUSES}
    previous_ids = {r["order_id"] for r in history.previous_rows}

    rows: list[Row] = []
    for oid in _sample_sorted(rng, open_ids & previous_ids, N_DAILY_UPDATES, "updates"):
        rows.append(_new_version(rng, history.latest[oid], during(day_start)))
    used = {r["order_id"] for r in rows}

    first = first_order_number(file_date)
    for n in range(first, first + N_DAILY_NEW_ORDERS):
        ts = _fmt(during(day_start))
        rows.append(
            {
                "order_id": f"ORD-{n:05d}",
                "organization_id": f"ORG-{rng.randint(1, N_ORGANIZATIONS_WITH_ORDERS):03d}",
                "investor_id": _investor(rng),
                "fund_id": f"FND-{rng.randint(1, N_FUNDS):03d}",
                "amount": _amount(rng),
                "currency": rng.choice(CURRENCIES),
                "channel": rng.choice(CHANNELS),
                "status": "submitted",
                "submitted_at": ts,
                "updated_at": ts,
            }
        )

    late_day = day_start - timedelta(days=LATE_DAYS_BEFORE)
    late_ids = {
        oid for oid in open_ids - used if history.latest[oid]["updated_at"] < _fmt(late_day)
    }
    for oid in _sample_sorted(rng, late_ids, N_DAILY_LATE_VERSIONS, "late versions"):
        rows.append(_new_version(rng, history.latest[oid], during(late_day)))
        used.add(oid)

    if plant_cross_file_conflict:
        rows.extend(_cross_file_conflicts(rng, history, used))

    for r in rows:
        oid = r["order_id"]
        if oid not in history.frozen:
            history.latest[oid] = r
    rows.sort(key=lambda r: (r["updated_at"], r["order_id"]))
    assert len(rows) == (N_DAILY_ROWS_WITH_CONFLICT if plant_cross_file_conflict else N_DAILY_ROWS)
    history.previous_rows = rows
    return [_with_contract_order(r) for r in rows]


def _cross_file_conflicts(rng: random.Random, history: _History, used: set[str]) -> list[Row]:
    """Copies of previous-file rows whose key is unique there; only the amount changes.

    The conflicted orders are frozen: no later file touches them again.
    """
    key_counts: dict[tuple[str, str], int] = {}
    for r in history.previous_rows:
        key = (r["order_id"], r["updated_at"])
        key_counts[key] = key_counts.get(key, 0) + 1
    candidates = [
        r
        for r in history.previous_rows
        if r["order_id"] not in history.frozen
        and r["order_id"] not in used
        and key_counts[(r["order_id"], r["updated_at"])] == 1
    ]
    if len(candidates) < N_DAILY_CROSS_FILE_CONFLICTS:
        raise RuntimeError("not enough candidate rows for cross-file conflicts")
    copies: list[Row] = []
    for original in rng.sample(candidates, N_DAILY_CROSS_FILE_CONFLICTS):
        copy = dict(original)
        while copy["amount"] == original["amount"]:
            copy["amount"] = _amount(rng)
        copies.append(copy)
        history.frozen.add(original["order_id"])
        history.latest.pop(original["order_id"], None)
    return copies


def iter_daily_files(
    seed: int = SEED, plant_cross_file_conflict: bool = False
) -> Iterator[tuple[date, list[Row]]]:
    """Yield ``(file_date, rows)`` from the base date on, one day at a time, forever.

    With ``plant_cross_file_conflict`` every daily file of the chain gets one cross-file
    conflict, so the bytes of a date depend on the flag but never on how it is called.
    """
    base_rows, planted_ids = _generate_base(seed)
    yield BASE_DATE, base_rows
    latest: dict[str, Row] = {}
    for r in base_rows:
        oid = r["order_id"]
        if oid not in planted_ids and (
            oid not in latest or r["updated_at"] > latest[oid]["updated_at"]
        ):
            latest[oid] = r
    history = _History(latest=latest, frozen=set(planted_ids), previous_rows=base_rows)
    file_date = BASE_DATE
    while True:
        file_date += timedelta(days=1)
        rng = random.Random(day_seed(file_date, seed))
        yield file_date, _daily_rows(rng, file_date, history, plant_cross_file_conflict)


def generate_orders_for_date(
    file_date: date, seed: int = SEED, plant_cross_file_conflict: bool = False
) -> list[Row]:
    """Rows of the file of ``file_date``: the base sample or a daily incremental file."""
    if file_date < BASE_DATE:
        raise ValueError(f"the first file date is {BASE_DATE.isoformat()}")
    for d, rows in iter_daily_files(seed, plant_cross_file_conflict):
        if d == file_date:
            return rows
    raise AssertionError("unreachable")


def output_name(file_date: date) -> str:
    return f"orders_{file_date.isoformat()}.csv"


def write_csv(rows: list[Row], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow([row[c] for c in COLUMNS] + list(row.get(EXTRA_FIELDS_KEY, [])))


_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _parse_date(value: str) -> date:
    if not _DATE_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("not a valid calendar date") from None
    if parsed < BASE_DATE:
        raise argparse.ArgumentTypeError(f"the first file date is {BASE_DATE.isoformat()}")
    return parsed


def _positive_int(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        n = 0
    if n < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic orders by logical date.")
    parser.add_argument(
        "--date",
        type=_parse_date,
        default=BASE_DATE,
        help=f"Logical file date, YYYY-MM-DD (default and first date {BASE_DATE.isoformat()}).",
    )
    parser.add_argument(
        "--days", type=_positive_int, default=1, help="Consecutive days to write (default 1)."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw/orders"),
        help="Directory for orders_<date>.csv (default data/raw/orders).",
    )
    parser.add_argument("--output", type=Path, help="Exact path of the CSV (only with --days 1).")
    parser.add_argument("--seed", type=int, default=SEED, help="Base seed (default 42).")
    parser.add_argument(
        "--plant-cross-file-conflict",
        action="store_true",
        help=(
            "Plant one cross-file version conflict in every daily file (off by default; "
            "dbt quarantines the conflicted order, ADR-0009)."
        ),
    )
    args = parser.parse_args(argv)
    if args.output is not None and args.days != 1:
        parser.error("--output works only with --days 1; use --output-dir")

    last = args.date + timedelta(days=args.days - 1)
    for file_date, rows in iter_daily_files(args.seed, args.plant_cross_file_conflict):
        if file_date < args.date:
            continue
        output = args.output or args.output_dir / output_name(file_date)
        write_csv(rows, output)
        print(f"{len(rows)} rows written to {output.name}")
        if file_date == last:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
