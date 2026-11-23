"""Extend the synthetic ``fx_rates`` seed to the MVP horizon (ADR-0013).

Standard library only (ADR-0004). The rates are synthetic: no market data and no
network calls.

The seed has two parts:

* the base period, 2026-11-01 to ``BASE_END`` (2026-11-12), written by hand for the
  sample's ``submitted_at`` dates. It is kept byte for byte;
* every later day up to ``HORIZON_END``, generated here as a deterministic random
  walk that starts from the ``BASE_END`` rates (``random.Random(SEED)``, small daily
  moves). The same base rows always give the same bytes.

Daily order files (``generate_orders --date``) submit new orders on the file date,
so the horizon covers every file date from the base sample (2026-11-19) to
``HORIZON_END``, including the MVP-10 backfill dates (TS-037). An order submitted
after ``HORIZON_END`` has no rate and the dbt test ``assert_every_order_has_fx_rate``
(TS-020) fails the build; move ``HORIZON_END`` and rerun this script to go further.

Usage:
    uv run python -m ingestion.generate_fx_rates            # rewrite the seed
    uv run python -m ingestion.generate_fx_rates --check    # exit 1 if the seed is stale
"""

from __future__ import annotations

import argparse
import csv
import io
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

SEED_FILE = Path(__file__).resolve().parents[1] / "transform" / "seeds" / "fx_rates.csv"
HEADER: tuple[str, ...] = ("rate_date", "currency", "rate_to_usd")
CURRENCIES: tuple[str, ...] = ("BRL", "EUR", "USD")  # the seed's order within a day

BASE_START = date(2026, 11, 1)
BASE_END = date(2026, 11, 12)  # last hand-written day, kept as is
HORIZON_END = date(2026, 12, 31)  # last day with a rate
SEED = 2026
# Daily standard deviation of the relative move, per currency (USD stays 1).
DAILY_VOLATILITY: dict[str, float] = {"BRL": 0.004, "EUR": 0.002}
# Plausible bands for the synthetic walk; a move that leaves the band is reflected.
BANDS: dict[str, tuple[Decimal, Decimal]] = {
    "BRL": (Decimal("0.160000"), Decimal("0.190000")),
    "EUR": (Decimal("1.040000"), Decimal("1.130000")),
}
_SIX_PLACES = Decimal("0.000001")

Rate = tuple[date, str, Decimal]


def read_seed(path: Path = SEED_FILE) -> list[Rate]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        if tuple(next(reader)) != HEADER:
            raise ValueError(f"unexpected header in {path.name}")
        return [(date.fromisoformat(d), c, Decimal(r)) for d, c, r in reader]


def _base_rows(rows: list[Rate]) -> list[Rate]:
    base = [r for r in rows if r[0] <= BASE_END]
    expected = {
        (BASE_START + timedelta(days=i), c)
        for i in range((BASE_END - BASE_START).days + 1)
        for c in CURRENCIES
    }
    if {(d, c) for d, c, _ in base} != expected or len(base) != len(expected):
        raise ValueError("the base period must have one rate per day and currency")
    return base


def _step(rng: random.Random, currency: str, rate: Decimal) -> Decimal:
    low, high = BANDS[currency]
    move = Decimal(repr(rng.gauss(0.0, DAILY_VOLATILITY[currency])))
    new = (rate * (1 + move)).quantize(_SIX_PLACES, rounding=ROUND_HALF_EVEN)
    if new > high:
        new = high - (new - high)
    elif new < low:
        new = low + (low - new)
    return new


def extend_rates(rows: list[Rate]) -> list[Rate]:
    """The base period of ``rows`` followed by one generated rate per day and currency."""
    base = _base_rows(rows)
    current = {c: r for d, c, r in base if d == BASE_END}
    rng = random.Random(SEED)
    out = list(base)
    day = BASE_END
    while day < HORIZON_END:
        day += timedelta(days=1)
        for currency in CURRENCIES:
            if currency != "USD":
                current[currency] = _step(rng, currency, current[currency])
            out.append((day, currency, current[currency]))
    return out


def render(rows: list[Rate]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADER)
    for day, currency, rate in rows:
        writer.writerow([day.isoformat(), currency, f"{rate:.6f}"])
    return buffer.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extend the synthetic fx_rates seed.")
    parser.add_argument("--seed-file", type=Path, default=SEED_FILE)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit 1 if the seed is stale.",
    )
    args = parser.parse_args(argv)
    current = args.seed_file.read_text(encoding="utf-8")
    expected = render(extend_rates(read_seed(args.seed_file)))
    if args.check:
        if current != expected:
            print(
                f"{args.seed_file.name} is stale: run python -m ingestion.generate_fx_rates"
            )
            return 1
        print(
            f"{args.seed_file.name} is up to date (through {HORIZON_END.isoformat()})"
        )
        return 0
    args.seed_file.write_text(expected, encoding="utf-8")
    print(f"{len(expected.splitlines()) - 1} rates written to {args.seed_file.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
