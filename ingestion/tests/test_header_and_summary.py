"""Header hardening (T-026, ADR-0017 C5) and ``--summary-json`` (MVP-04).

All data is fictitious and built inside the test itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion import validate_orders as vo
from ingestion.tests.test_validate_orders import (
    HEADER,
    RUN_TS,
    make_row,
    run_cli,
    run_validator,
    write_input,
)


@pytest.fixture
def dirs(tmp_path: Path) -> dict[str, Path]:
    return {
        "staging": tmp_path / "out" / "staging" / "orders",
        "quarantine": tmp_path / "out" / "quarantine" / "orders",
    }


def write_raw(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    lines = [",".join(header)] + [",".join(r) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def validate_with_summary(src: Path, dirs: dict[str, Path], summary: Path) -> int:
    return vo.main(
        [
            "--input", str(src),
            "--run-ts", RUN_TS,
            "--staging-dir", str(dirs["staging"]),
            "--quarantine-dir", str(dirs["quarantine"]),
            "--summary-json", str(summary),
        ]
    )


# --- TS-024 (header part): reserved, duplicated and off-contract columns ----


@pytest.mark.parametrize("reserved", ["_source_file", "_loaded_at", "reject_reason"])
def test_ts024_reserved_column_exits_2_without_outputs(tmp_path, dirs, capsys, reserved):
    row = list(make_row("ORD-00001").values()) + ["x"]
    src = write_raw(tmp_path / "orders_r.csv", HEADER + [reserved], [row])

    assert run_validator(src, dirs) == 2

    err = capsys.readouterr().err
    assert "reserved" in err and reserved in err
    assert not dirs["staging"].exists()
    assert not dirs["quarantine"].exists()


def test_ts024_duplicated_column_exits_2_without_outputs(tmp_path, dirs, capsys):
    row = list(make_row("ORD-00001").values()) + ["ORD-00002"]
    src = write_raw(tmp_path / "orders_dup.csv", HEADER + ["order_id"], [row])

    assert run_validator(src, dirs) == 2

    err = capsys.readouterr().err
    assert "duplicated" in err and "order_id" in err
    assert not dirs["staging"].exists()
    assert not dirs["quarantine"].exists()


def test_ts024_off_contract_column_exits_2_without_outputs(tmp_path, dirs, capsys):
    """C5: a column without a pii_level never enters staging; the whole file is rejected."""
    row = list(make_row("ORD-00001").values()) + ["NAME-0001"]
    src = write_raw(tmp_path / "orders_off.csv", HEADER + ["investor_name"], [row])

    assert run_validator(src, dirs) == 2

    err = capsys.readouterr().err
    assert "outside the contract" in err
    assert f"position(s): {len(HEADER) + 1}" in err
    # The off-contract name comes from the file: it is reported by position only.
    assert "investor_name" not in err
    assert "NAME-0001" not in err
    assert not dirs["staging"].exists()
    assert not dirs["quarantine"].exists()


def test_ts024_header_rejection_keeps_previous_outputs(tmp_path, dirs):
    src = write_input(tmp_path / "orders_keep.csv", [make_row("ORD-00001")])
    assert run_validator(src, dirs) == 0
    before = (dirs["staging"] / src.name).read_bytes()

    write_raw(src, HEADER + ["extra"], [list(make_row("ORD-00009").values()) + ["x"]])
    assert run_validator(src, dirs) == 2

    assert (dirs["staging"] / src.name).read_bytes() == before
    assert sorted(p.name for p in dirs["staging"].iterdir()) == [src.name]


@pytest.mark.parametrize(
    "header, expected",
    [
        (HEADER, None),
        (list(reversed(HEADER)), None),
        (HEADER[1:], "missing required column(s): order_id"),
        (HEADER[1:] + ["_loaded_at"], "missing required column(s): order_id"),
        (
            HEADER + ["reject_reason", "_source_file"],
            "reserved column name(s): _source_file, reject_reason",
        ),
        (HEADER + ["a", "b"], f"position(s): {len(HEADER) + 1}, {len(HEADER) + 2}"),
        (HEADER + [""], f"position(s): {len(HEADER) + 1}"),
        ([" order_id"] + HEADER, "position(s): 1"),
        (HEADER + ["currency", "status"], "duplicated column(s): currency, status"),
    ],
    ids=[
        "valid", "reordered", "missing_first", "missing_wins_over_reserved",
        "reserved_in_order", "off_contract", "empty_name", "padded_name", "duplicated",
    ],
)
def test_header_error(header, expected):
    error = vo.header_error(header)
    if expected is None:
        assert error is None
    else:
        assert expected in error


def test_header_error_empty_file_is_missing_everything():
    assert vo.header_error(None).startswith("header is missing required column(s): order_id")


# --- --summary-json ----------------------------------------------------------


def test_summary_json_has_counts_and_reason_codes(tmp_path, dirs):
    rows = [
        make_row("ORD-00001"),
        make_row("ORD-00002", amount=""),
        make_row("ORD-00003", channel="   "),
        make_row("ORD-00001"),  # exact duplicate
    ]
    src = write_input(tmp_path / "orders_s.csv", rows)
    summary = tmp_path / "reports" / "summary.json"

    assert validate_with_summary(src, dirs, summary) == 0

    assert json.loads(summary.read_text(encoding="utf-8")) == {
        "source_file": "orders_s.csv",
        "input_rows": 4,
        "staging_rows": 2,
        "quarantine_rows": 2,
        "reasons": {"missing_amount": 1, "missing_channel": 1},
        "exact_duplicates": 1,
        "versioned_orders": 0,
        "reconciled": True,
    }
    assert not [p for p in summary.parent.iterdir() if p.suffix == ".tmp"]


def test_summary_json_never_contains_field_values(tmp_path, dirs):
    """G-1/G-2: only counts, reason codes and the file name; no row content."""
    sentinel = {col: f"SENTINEL-{i:02d}-VALUE" for i, col in enumerate(HEADER)}
    good = {**sentinel, "updated_at": "SENTINEL-T1"}
    blank = {**sentinel, "updated_at": "SENTINEL-T2", "fund_id": ""}
    conflict_a = {**sentinel, "updated_at": "SENTINEL-T3"}
    conflict_b = {**sentinel, "updated_at": "SENTINEL-T3", "amount": "SENTINEL-OTHER"}
    src = write_input(tmp_path / "orders_g.csv", [good, blank, conflict_a, conflict_b])
    summary = tmp_path / "reports" / "summary.json"

    assert validate_with_summary(src, dirs, summary) == 0

    text = summary.read_text(encoding="utf-8")
    assert "SENTINEL" not in text
    assert str(tmp_path) not in text
    data = json.loads(text)
    assert (data["staging_rows"], data["quarantine_rows"]) == (1, 3)
    assert data["reasons"] == {"conflicting_version": 2, "missing_fund_id": 1}


def test_summary_json_header_only_file(tmp_path, dirs):
    src = write_input(tmp_path / "orders_empty.csv", [])
    summary = tmp_path / "reports" / "summary.json"

    assert validate_with_summary(src, dirs, summary) == 0

    data = json.loads(summary.read_text(encoding="utf-8"))
    assert (data["input_rows"], data["staging_rows"], data["quarantine_rows"]) == (0, 0, 0)
    assert data["reasons"] == {}


def test_summary_json_not_written_on_exit_2(tmp_path, dirs):
    src = write_input(tmp_path / "orders_bad.csv", [make_row("ORD-00001")], header=HEADER[1:])
    summary = tmp_path / "reports" / "summary.json"

    assert validate_with_summary(src, dirs, summary) == 2
    assert not summary.exists()


def test_summary_json_not_written_on_exit_1(tmp_path, dirs, monkeypatch):
    src = write_input(tmp_path / "orders_rec.csv", [make_row("ORD-00001")])
    summary = tmp_path / "reports" / "summary.json"
    monkeypatch.setattr(vo, "count_data_rows", lambda path: 0)

    assert validate_with_summary(src, dirs, summary) == 1
    assert not summary.exists()
    assert not dirs["staging"].joinpath(src.name).exists()


@pytest.mark.parametrize(
    "target", ["input", "input_dir", "staging", "quarantine", "directory"]
)
def test_summary_json_cannot_collide_with_other_files(tmp_path, dirs, capsys, target):
    src = write_input(tmp_path / "orders_c.csv", [make_row("ORD-00001")])
    summary = {
        "input": src,
        "input_dir": src.parent / "summary.json",
        "staging": dirs["staging"] / src.name,
        "quarantine": dirs["quarantine"] / src.name,
        "directory": tmp_path,
    }[target]
    before = src.read_bytes()

    assert validate_with_summary(src, dirs, summary) == 2

    assert "--summary-json" in capsys.readouterr().err
    assert src.read_bytes() == before
    assert not (src.parent / "summary.json").exists()
    assert not dirs["staging"].exists()


def test_summary_json_is_optional_and_does_not_change_stdout(tmp_path, dirs, capsys):
    src = write_input(tmp_path / "orders_o.csv", [make_row("ORD-00001")])
    assert run_validator(src, dirs) == 0
    plain = capsys.readouterr().out
    assert validate_with_summary(src, dirs, tmp_path / "reports" / "summary.json") == 0
    assert capsys.readouterr().out == plain


def test_summary_json_via_cli(tmp_path, dirs):
    src = write_input(tmp_path / "orders_cli.csv", [make_row("ORD-00001")])
    summary = tmp_path / "reports" / "summary.json"
    result = run_cli(
        "--input", str(src),
        "--run-ts", RUN_TS,
        "--staging-dir", str(dirs["staging"]),
        "--quarantine-dir", str(dirs["quarantine"]),
        "--summary-json", str(summary),
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(summary.read_text(encoding="utf-8"))["staging_rows"] == 1
