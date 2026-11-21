"""Tests for the quarantine batch guard (ADR-0017, T4; MVP-04).

All data is fictitious and built inside the test itself, except the versioned sample.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ingestion import batch_guard as bg
from ingestion import validate_orders as vo
from ingestion.tests.test_validate_orders import HEADER, RUN_TS, make_row, write_input

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_FILE = REPO_ROOT / "data" / "raw" / "orders" / "orders_2026-11-19.csv"


def validate(src: Path, out: Path) -> Path:
    summary = out / "summary.json"
    code = vo.run(src, RUN_TS, out / "staging", out / "quarantine", summary_json=summary)
    assert code == 0
    return summary


def write_summary(path: Path, **overrides) -> Path:
    data = {
        "source_file": "orders_x.csv",
        "input_rows": 10,
        "staging_rows": 9,
        "quarantine_rows": 1,
        "reasons": {"missing_amount": 1},
        "exact_duplicates": 0,
        "versioned_orders": 0,
        "reconciled": True,
    }
    data.update(overrides)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# --- Pure function ------------------------------------------------------------


def test_default_limit_is_ten_percent():
    assert bg.DEFAULT_MAX_QUARANTINE_RATIO == 0.10


@pytest.mark.parametrize(
    "input_rows, quarantine_rows, passed",
    [
        (284, 12, True),  # the sample: 4.2%
        (10, 3, False),  # 30%
        (0, 0, True),  # header only (TS-005)
        (10, 1, True),  # exactly at the limit
        (1000, 101, False),  # just above the limit
        (10, 0, True),
        (5, 5, False),
    ],
)
def test_check_batch(input_rows, quarantine_rows, passed):
    assert bg.check_batch(input_rows, quarantine_rows).passed is passed


def test_check_batch_limit_is_configurable():
    assert bg.check_batch(10, 3, max_ratio=0.30).passed
    assert not bg.check_batch(10, 1, max_ratio=0.0).passed
    assert bg.check_batch(10, 10, max_ratio=1.0).passed


@pytest.mark.parametrize("max_ratio", [-0.01, 1.01, float("nan"), float("inf"), True, "0.1"])
def test_check_batch_rejects_invalid_limit(max_ratio):
    with pytest.raises(bg.InvalidInputError):
        bg.check_batch(10, 1, max_ratio=max_ratio)


@pytest.mark.parametrize("counts", [(-1, 0), (1, -1), (3, 4), (1.0, 0), (True, 0)])
def test_check_batch_rejects_invalid_counts(counts):
    with pytest.raises(bg.InvalidInputError):
        bg.check_batch(*counts)


def test_ratio_and_render():
    result = bg.check_batch(284, 12)
    assert result.ratio == pytest.approx(12 / 284)
    assert result.render() == "quarantine ratio: 12/284 = 4.2% (limit 10.0%): OK"


# --- Summary checks -----------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"input_rows": "10"},
        {"quarantine_rows": None},
        {"staging_rows": -1},
        {"reconciled": False},
        {"staging_rows": 8},  # 10 != 8 + 1
    ],
)
def test_check_summary_rejects_invalid_summary(tmp_path, overrides):
    path = write_summary(tmp_path / "s.json", **overrides)
    with pytest.raises(bg.InvalidInputError):
        bg.check_summary(bg.load_summary(path))


def test_check_summary_rejects_non_object():
    with pytest.raises(bg.InvalidInputError):
        bg.check_summary([1, 2, 3])


# --- End to end: validator summary -> guard ------------------------------------


def test_sample_passes(tmp_path, capsys):
    """The versioned sample (12/284 = 4.2%) passes the default limit."""
    summary = validate(RAW_FILE, tmp_path)
    capsys.readouterr()

    assert bg.main(["--summary-json", str(summary)]) == 0
    assert "12/284 = 4.2%" in capsys.readouterr().out


def test_thirty_percent_fixture_fails(tmp_path, capsys):
    rows = [make_row(f"ORD-{i:05d}") for i in range(1, 8)]
    rows += [make_row(f"ORD-{i:05d}", amount="") for i in range(8, 11)]
    src = write_input(tmp_path / "orders_30.csv", rows)
    summary = validate(src, tmp_path)
    capsys.readouterr()

    assert bg.main(["--summary-json", str(summary)]) == 1

    captured = capsys.readouterr()
    assert "3/10 = 30.0%" in captured.out
    assert "above the limit" in captured.err


def test_thirty_percent_fixture_passes_with_a_higher_limit(tmp_path):
    rows = [make_row(f"ORD-{i:05d}") for i in range(1, 8)]
    rows += [make_row(f"ORD-{i:05d}", status="") for i in range(8, 11)]
    summary = validate(write_input(tmp_path / "orders_30b.csv", rows), tmp_path)

    assert bg.main(["--summary-json", str(summary), "--max-quarantine-ratio", "0.3"]) == 0


def test_header_only_file_passes(tmp_path):
    """TS-005: zero input rows is not a division by zero and passes."""
    summary = validate(write_input(tmp_path / "orders_empty.csv", []), tmp_path)

    assert bg.main(["--summary-json", str(summary)]) == 0


# --- CLI errors ---------------------------------------------------------------


def test_missing_summary_exits_2_with_file_name_only(tmp_path, capsys):
    missing = tmp_path / "nested" / "nope.json"
    assert bg.main(["--summary-json", str(missing)]) == 2
    err = capsys.readouterr().err
    assert "nope.json" in err
    assert str(tmp_path) not in err


@pytest.mark.parametrize("payload", [b"{not json", b"\xff\xfe\x00"])
def test_unreadable_summary_exits_2(tmp_path, capsys, payload):
    path = tmp_path / "bad.json"
    path.write_bytes(payload)
    assert bg.main(["--summary-json", str(path)]) == 2
    assert "bad.json is not valid JSON" in capsys.readouterr().err


@pytest.mark.parametrize("limit", ["-0.5", "2", "nan"])
def test_invalid_limit_exits_2(tmp_path, limit):
    path = write_summary(tmp_path / "s.json")
    assert bg.main(["--summary-json", str(path), "--max-quarantine-ratio", limit]) == 2


def test_unexpected_error_exits_3_without_exception_text(tmp_path, monkeypatch, capsys):
    def boom(path):
        raise RuntimeError("SECRET-VALUE")

    monkeypatch.setattr(bg, "load_summary", boom)
    assert bg.main(["--summary-json", str(tmp_path / "s.json")]) == 3
    err = capsys.readouterr().err
    assert "RuntimeError" in err
    assert "SECRET-VALUE" not in err


def test_cli_module_entrypoint(tmp_path):
    path = write_summary(tmp_path / "s.json", input_rows=10, staging_rows=7, quarantine_rows=3)
    result = subprocess.run(
        [sys.executable, "-m", "ingestion.batch_guard", "--summary-json", str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "30.0%" in result.stdout


def test_header_constant_is_the_contract():
    assert HEADER == list(vo.REQUIRED_COLUMNS)
