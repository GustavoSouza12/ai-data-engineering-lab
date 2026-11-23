"""Tests of the fx_rates seed extension (ADR-0013, TS-020 horizon)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ingestion import generate_fx_rates as fx
from ingestion.generate_orders import BASE_DATE, iter_daily_files


@pytest.fixture(scope="module")
def seed_rows() -> list[fx.Rate]:
    return fx.read_seed()


def test_committed_seed_is_up_to_date():
    assert fx.main(["--check"]) == 0


def test_seed_has_one_rate_per_day_and_currency_through_the_horizon(seed_rows):
    keys = [(d, c) for d, c, _ in seed_rows]
    assert len(keys) == len(set(keys))
    n_days = (fx.HORIZON_END - fx.BASE_START).days + 1
    assert set(keys) == {
        (fx.BASE_START + timedelta(days=i), c)
        for i in range(n_days)
        for c in fx.CURRENCIES
    }
    assert keys == sorted(keys)


def test_rates_are_plausible(seed_rows):
    for day, currency, rate in seed_rows:
        if currency == "USD":
            assert rate == Decimal("1.000000"), day
        else:
            low, high = fx.BANDS[currency]
            assert low <= rate <= high, (day, currency, rate)
            assert rate == rate.quantize(Decimal("0.000001"))


def test_base_period_is_kept_and_later_rows_are_regenerated(seed_rows):
    base = [r for r in seed_rows if r[0] <= fx.BASE_END]
    assert len(base) == 36
    # Rows after the base period do not influence the result.
    tampered = base + [(fx.BASE_END + timedelta(days=1), "EUR", Decimal("9.999999"))]
    assert fx.extend_rates(tampered) == seed_rows
    assert fx.extend_rates(base)[: len(base)] == base


def test_extension_is_deterministic(seed_rows):
    base = [r for r in seed_rows if r[0] <= fx.BASE_END]
    assert fx.render(fx.extend_rates(base)) == fx.render(fx.extend_rates(base))


def test_base_period_with_a_missing_day_is_rejected(seed_rows):
    holed = [r for r in seed_rows if r[0] != date(2026, 11, 5)]
    with pytest.raises(ValueError, match="one rate per day and currency"):
        fx.extend_rates(holed)


def test_check_reports_a_stale_seed(tmp_path: Path, seed_rows):
    stale = tmp_path / "fx_rates.csv"
    stale.write_text(
        fx.render([r for r in seed_rows if r[0] <= fx.BASE_END]), encoding="utf-8"
    )
    assert fx.main(["--seed-file", str(stale), "--check"]) == 1
    assert fx.main(["--seed-file", str(stale)]) == 0
    assert fx.main(["--seed-file", str(stale), "--check"]) == 0
    assert stale.read_text(encoding="utf-8") == fx.render(seed_rows)


def test_every_generated_order_up_to_the_horizon_has_a_rate(seed_rows):
    """Every file date the generator can write up to HORIZON_END, so every backfill
    inside it (TS-037), submits orders on dates and currencies that have a rate."""
    rates = {(d, c) for d, c, _ in seed_rows}
    n_files = 0
    for file_date, rows in iter_daily_files():
        for row in rows:
            submitted, currency = row["submitted_at"], row["currency"]
            if not submitted.strip() or currency not in fx.CURRENCIES:
                continue  # planted structural errors: they go to quarantine
            assert (date.fromisoformat(submitted[:10]), currency) in rates, row[
                "order_id"
            ]
        n_files += 1
        if file_date == fx.HORIZON_END:
            break
    assert n_files == (fx.HORIZON_END - BASE_DATE).days + 1
