"""Tests for the structural validation of orders (ADR-0002 and ADR-0009).

All data is fictitious and built inside the test itself.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

from ingestion import validate_orders as vo

HEADER = list(vo.REQUIRED_COLUMNS)
RUN_TS = "2026-11-19T03:00:00Z"
REPO_ROOT = Path(__file__).resolve().parents[2]


def make_row(oid: str, **overrides: str) -> dict[str, str]:
    row = {
        "order_id": oid,
        "organization_id": "ORG-001",
        "investor_id": "INV-0001",
        "fund_id": "FND-001",
        "amount": "1000.00",
        "currency": "USD",
        "channel": "advisor",
        "status": "submitted",
        "submitted_at": "2026-11-02T10:00:00",
        "updated_at": "2026-11-02T10:00:00",
    }
    row.update(overrides)
    return row


def write_input(path: Path, rows: list[dict[str, str]], header: list[str] = HEADER) -> Path:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def read_output(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture
def dirs(tmp_path: Path) -> dict[str, Path]:
    return {
        "staging": tmp_path / "out" / "staging" / "orders",
        "quarantine": tmp_path / "out" / "quarantine" / "orders",
    }


def run_validator(input_path: Path, dirs: dict[str, Path], run_ts: str = RUN_TS) -> int:
    return vo.main(
        [
            "--input", str(input_path),
            "--run-ts", run_ts,
            "--staging-dir", str(dirs["staging"]),
            "--quarantine-dir", str(dirs["quarantine"]),
        ]
    )


def all_files(*directories: Path) -> list[str]:
    return sorted(p.name for d in directories if d.exists() for p in d.iterdir())


# --- TS-001 ----------------------------------------------------------------


def test_ts001_complete_row_goes_to_staging(tmp_path, dirs):
    src = write_input(tmp_path / "orders_a.csv", [make_row("ORD-00001")])

    assert run_validator(src, dirs) == 0

    staging = read_output(dirs["staging"] / "orders_a.csv")
    quarantine = read_output(dirs["quarantine"] / "orders_a.csv")
    assert quarantine == []
    assert len(staging) == 1
    assert staging[0]["order_id"] == "ORD-00001"
    assert staging[0]["_source_file"] == "orders_a.csv"  # name, not path
    assert staging[0]["_loaded_at"] == RUN_TS
    assert list(staging[0].keys()) == HEADER + ["_source_file", "_loaded_at"]


def test_contract_columns_in_order():
    assert vo.REQUIRED_COLUMNS == (
        "order_id", "organization_id", "investor_id", "fund_id", "amount",
        "currency", "channel", "status", "submitted_at", "updated_at",
    )


# --- TS-002 ----------------------------------------------------------------


@pytest.mark.parametrize("value", ["", "   ", "\t"])
@pytest.mark.parametrize("column", vo.REQUIRED_COLUMNS)
def test_ts002_blank_or_whitespace_goes_to_quarantine(tmp_path, dirs, column, value):
    src = write_input(
        tmp_path / "orders_b.csv",
        [make_row("ORD-00001"), make_row("ORD-00002", **{column: value})],
    )

    assert run_validator(src, dirs) == 0

    staging = read_output(dirs["staging"] / "orders_b.csv")
    quarantine = read_output(dirs["quarantine"] / "orders_b.csv")
    assert [r["order_id"] for r in staging] == ["ORD-00001"]
    assert len(quarantine) == 1
    assert quarantine[0]["reject_reason"] == f"missing_{column}"
    assert quarantine[0][column] == value  # original value preserved


def test_ts002_multiple_reasons_in_stable_order():
    rows = [
        make_row("ORD-00001", channel="", fund_id=" "),
        make_row("ORD-00001", amount="2000.00"),
    ]
    rows[0][vo.EXTRA_FIELDS_KEY] = ["x", "y"]
    staging, quarantine = vo.split_rows(rows, source_file="x.csv", loaded_at=RUN_TS)
    assert staging == []
    assert quarantine[0]["reject_reason"] == (
        "missing_fund_id;missing_channel;conflicting_version;extra_fields:2"
    )
    assert quarantine[1]["reject_reason"] == "conflicting_version"


def test_short_row_is_missing_fields(tmp_path, dirs):
    src = tmp_path / "orders_short.csv"
    src.write_text(",".join(HEADER) + "\nORD-00001,ORG-001,INV-0001\n", encoding="utf-8")

    assert run_validator(src, dirs) == 0

    quarantine = read_output(dirs["quarantine"] / src.name)
    assert quarantine[0]["reject_reason"] == ";".join(f"missing_{c}" for c in HEADER[3:])


# --- TS-004 ----------------------------------------------------------------


def test_ts004_missing_header_column_exits_2_without_outputs(tmp_path, dirs, capsys):
    header = [c for c in HEADER if c != "updated_at"]
    src = write_input(tmp_path / "orders_d.csv", [make_row("ORD-00001")], header=header)

    assert run_validator(src, dirs) == 2

    err = capsys.readouterr().err
    assert "updated_at" in err
    assert not dirs["staging"].exists()
    assert not dirs["quarantine"].exists()


def test_ts004_missing_header_does_not_touch_existing_outputs(tmp_path, dirs):
    good = write_input(tmp_path / "orders_d.csv", [make_row("ORD-00001")])
    assert run_validator(good, dirs) == 0
    before_stg = (dirs["staging"] / "orders_d.csv").read_bytes()
    before_q = (dirs["quarantine"] / "orders_d.csv").read_bytes()

    write_input(good, [make_row("ORD-00009")], header=HEADER[1:])
    assert run_validator(good, dirs) == 2

    assert (dirs["staging"] / "orders_d.csv").read_bytes() == before_stg
    assert (dirs["quarantine"] / "orders_d.csv").read_bytes() == before_q
    assert sorted(p.name for p in dirs["staging"].iterdir()) == ["orders_d.csv"]


def test_f4_header_order_is_not_required_and_is_preserved(tmp_path, dirs):
    """The validator requires the columns to be present, not ordered; output follows input."""
    header = list(reversed(HEADER))
    src = write_input(tmp_path / "orders_rev.csv", [make_row("ORD-00001")], header=header)

    assert run_validator(src, dirs) == 0

    staging = read_output(dirs["staging"] / src.name)
    assert list(staging[0].keys()) == header + ["_source_file", "_loaded_at"]
    assert staging[0]["order_id"] == "ORD-00001"


def test_ts004_missing_input_file_exits_2(tmp_path, dirs):
    assert run_validator(tmp_path / "does_not_exist.csv", dirs) == 2
    assert not dirs["staging"].exists()


# --- TS-005 ----------------------------------------------------------------


def test_ts005_header_only_produces_header_only_outputs(tmp_path, dirs):
    src = write_input(tmp_path / "orders_e.csv", [])

    assert run_validator(src, dirs) == 0

    stg_lines = (dirs["staging"] / "orders_e.csv").read_text(encoding="utf-8").splitlines()
    q_lines = (dirs["quarantine"] / "orders_e.csv").read_text(encoding="utf-8").splitlines()
    assert stg_lines == [",".join(HEADER + ["_source_file", "_loaded_at"])]
    assert q_lines == [",".join(HEADER + ["_source_file", "_loaded_at", "reject_reason"])]


# --- TS-006 ----------------------------------------------------------------


def test_ts006_same_run_ts_is_byte_identical(tmp_path):
    rows = [
        make_row("ORD-00001"),
        make_row("ORD-00002", amount=""),
        make_row("ORD-00003"),
        make_row("ORD-00003"),
        make_row("ORD-00004"),
        make_row("ORD-00004", investor_id="INV-0002"),
    ]
    src = write_input(tmp_path / "orders_f.csv", rows)
    first = {"staging": tmp_path / "r1" / "stg", "quarantine": tmp_path / "r1" / "q"}
    second = {"staging": tmp_path / "r2" / "stg", "quarantine": tmp_path / "r2" / "q"}

    assert run_validator(src, first) == 0
    assert run_validator(src, second) == 0
    # Rerunning into the same directory does not change anything either.
    snapshot = (first["staging"] / "orders_f.csv").read_bytes()
    assert run_validator(src, first) == 0

    for key in ("staging", "quarantine"):
        assert (first[key] / "orders_f.csv").read_bytes() == (second[key] / "orders_f.csv").read_bytes()
        assert sorted(p.name for p in first[key].iterdir()) == ["orders_f.csv"]  # no temp files
    assert (first["staging"] / "orders_f.csv").read_bytes() == snapshot


def test_ts006_run_ts_is_required(tmp_path, dirs):
    src = write_input(tmp_path / "orders_f.csv", [make_row("ORD-00001")])
    with pytest.raises(SystemExit) as exc:
        vo.main(["--input", str(src)])
    assert exc.value.code == 2


def test_invalid_run_ts_exits_2_without_echoing_value(tmp_path, dirs, capsys):
    src = write_input(tmp_path / "orders_i.csv", [make_row("ORD-00001")])
    assert run_validator(src, dirs, run_ts="yesterday-SECRET") == 2
    err = capsys.readouterr().err
    assert "--run-ts is not a valid ISO 8601 timestamp" in err
    assert "SECRET" not in err  # T-026: the received value is never echoed
    assert not dirs["staging"].exists()


@pytest.mark.parametrize("run_ts", ["2026-11-19T03:00:00", "2026-11-19"])
def test_run_ts_without_timezone_exits_2(tmp_path, dirs, capsys, run_ts):
    src = write_input(tmp_path / "orders_tz.csv", [make_row("ORD-00001")])

    assert run_validator(src, dirs, run_ts=run_ts) == 2

    err = capsys.readouterr().err
    assert "--run-ts has no timezone" in err
    assert run_ts not in err  # T-026: the received value is never echoed
    assert not dirs["staging"].exists()
    assert not dirs["quarantine"].exists()


@pytest.mark.parametrize(
    ("run_ts", "expected"),
    [
        ("2026-11-19T03:00:00Z", "2026-11-19T03:00:00Z"),
        ("2026-11-19T03:00:00+00:00", "2026-11-19T03:00:00Z"),
        ("2026-11-18T22:00:00-05:00", "2026-11-19T03:00:00Z"),
        ("2026-11-19T06:00:00.123456+03:00", "2026-11-19T03:00:00Z"),
    ],
)
def test_loaded_at_is_normalized_to_utc(tmp_path, dirs, run_ts, expected):
    src = write_input(tmp_path / "orders_utc.csv", [make_row("ORD-00001")])

    assert run_validator(src, dirs, run_ts=run_ts) == 0

    staging = read_output(dirs["staging"] / "orders_utc.csv")
    assert staging[0]["_loaded_at"] == expected


# --- TS-007 ----------------------------------------------------------------


def test_ts007_reconciliation_input_equals_staging_plus_quarantine(tmp_path, dirs, capsys):
    rows = [
        make_row("ORD-00001"),
        make_row("ORD-00002", investor_id=""),
        make_row("ORD-00003"),
        make_row("ORD-00003"),  # exact duplicate: passes
        make_row("ORD-00004", amount="-5.00"),  # semantic: passes ingestion
        make_row("ORD-00005"),
        make_row("ORD-00005", amount="7.00"),  # conflict: both go to quarantine
    ]
    src = write_input(tmp_path / "orders_g.csv", rows)

    assert run_validator(src, dirs) == 0

    n_stg = len(read_output(dirs["staging"] / "orders_g.csv"))
    n_q = len(read_output(dirs["quarantine"] / "orders_g.csv"))
    assert (n_stg, n_q) == (4, 3)
    assert n_stg + n_q == len(rows)
    out = capsys.readouterr().out
    assert "input:      7" in out
    assert "reconciliation: OK (7 = 4 + 3)" in out


def test_ts007_reconcile_function():
    assert vo.reconcile(5, 3, 2)
    assert not vo.reconcile(5, 3, 1)


def test_ts007_failed_reconciliation_exits_1_and_publishes_nothing(
    tmp_path, dirs, monkeypatch, capsys
):
    src = write_input(tmp_path / "orders_h.csv", [make_row("ORD-00001")])
    monkeypatch.setattr(vo, "count_data_rows", lambda path: 0)  # simulates lost rows

    assert run_validator(src, dirs) == 1

    captured = capsys.readouterr()
    assert "reconciliation: FAILED" in captured.out
    assert "error: reconciliation failed; nothing published" in captured.err
    assert list(dirs["staging"].iterdir()) == []  # neither output nor temp file
    assert list(dirs["quarantine"].iterdir()) == []


# --- TS-013: versions pass ---------------------------------------------------


def test_ts013_versions_go_to_staging(tmp_path, dirs, capsys):
    rows = [
        make_row("ORD-00001", status="submitted", updated_at="2026-11-02T10:00:00"),
        make_row("ORD-00002"),
        make_row(
            "ORD-00001", status="approved", amount="1500.00", updated_at="2026-11-03T10:00:00"
        ),
        make_row("ORD-00001", status="completed", updated_at="2026-11-04T10:00:00"),
    ]
    src = write_input(tmp_path / "orders_v.csv", rows)

    assert run_validator(src, dirs) == 0

    staging = read_output(dirs["staging"] / "orders_v.csv")
    assert read_output(dirs["quarantine"] / "orders_v.csv") == []
    # Every version, in original order; picking the latest is the job of dbt.
    assert [(r["order_id"], r["status"]) for r in staging] == [
        ("ORD-00001", "submitted"),
        ("ORD-00002", "submitted"),
        ("ORD-00001", "approved"),
        ("ORD-00001", "completed"),
    ]
    assert "order_id with more than one version (dbt picks the latest): 1" in capsys.readouterr().out


# --- TS-014: exact duplicates pass -----------------------------------------


def test_ts014_exact_duplicates_go_to_staging(tmp_path, dirs, capsys):
    rows = [make_row("ORD-00001"), make_row("ORD-00002"), make_row("ORD-00001")]
    src = write_input(tmp_path / "orders_x.csv", rows)

    assert run_validator(src, dirs) == 0

    staging = read_output(dirs["staging"] / "orders_x.csv")
    assert [r["order_id"] for r in staging] == ["ORD-00001", "ORD-00002", "ORD-00001"]
    assert read_output(dirs["quarantine"] / "orders_x.csv") == []
    out = capsys.readouterr().out
    assert "exact duplicates (dbt deduplicates): 1" in out
    assert "order_id with more than one version (dbt picks the latest): 0" in out


def test_ts014_key_whitespace_is_ignored_in_comparison():
    rows = [make_row("ORD-00001"), make_row(" ORD-00001 ", updated_at="2026-11-02T10:00:00 ")]
    staging, quarantine = vo.split_rows(rows, source_file="x.csv", loaded_at=RUN_TS)
    assert quarantine == []
    assert [r["order_id"] for r in staging] == ["ORD-00001", " ORD-00001 "]  # original preserved
    assert vo.count_exact_duplicates(staging) == 1


# --- TS-015: conflict -------------------------------------------------------


@pytest.mark.parametrize("column", [c for c in vo.REQUIRED_COLUMNS if c not in vo.VERSION_KEY])
def test_ts015_conflict_sends_all_occurrences_to_quarantine(tmp_path, dirs, column):
    other_value = {"amount": "2000.00", "submitted_at": "2026-11-01T09:00:00"}.get(column, "OTHER")
    rows = [
        make_row("ORD-00117"),
        make_row("ORD-00001"),
        make_row("ORD-00117", **{column: other_value}),
        make_row("ORD-00117"),  # repeats the first one, but the group is in conflict
        make_row("ORD-00117", updated_at="2026-11-05T10:00:00"),  # another version: passes
    ]
    src = write_input(tmp_path / "orders_c.csv", rows)

    assert run_validator(src, dirs) == 0

    staging = read_output(dirs["staging"] / "orders_c.csv")
    quarantine = read_output(dirs["quarantine"] / "orders_c.csv")
    assert [(r["order_id"], r["updated_at"]) for r in staging] == [
        ("ORD-00001", "2026-11-02T10:00:00"),
        ("ORD-00117", "2026-11-05T10:00:00"),
    ]
    assert len(quarantine) == 3
    assert {r["reject_reason"] for r in quarantine} == {"conflicting_version"}
    assert [r[column] for r in quarantine] == [rows[0][column], other_value, rows[0][column]]


@pytest.mark.parametrize("value", ["", "   "])
@pytest.mark.parametrize("column", [c for c in vo.REQUIRED_COLUMNS if c not in vo.VERSION_KEY])
def test_f1_incomplete_row_with_same_key_as_complete_is_conflict(tmp_path, dirs, column, value):
    """ADR-0009, interpretation F1: both rows go to quarantine."""
    rows = [
        make_row("ORD-00050"),
        make_row("ORD-00051"),
        make_row("ORD-00050", **{column: value}),
    ]
    src = write_input(tmp_path / "orders_f1.csv", rows)

    assert run_validator(src, dirs) == 0

    staging = read_output(dirs["staging"] / src.name)
    quarantine = read_output(dirs["quarantine"] / src.name)
    assert [r["order_id"] for r in staging] == ["ORD-00051"]
    assert [r["reject_reason"] for r in quarantine] == [
        "conflicting_version",
        f"missing_{column};conflicting_version",
    ]
    assert vo.reason_counts(quarantine) == {"conflicting_version": 2, f"missing_{column}": 1}


def test_ts015_blank_keys_are_not_conflicts():
    rows = [make_row(""), make_row("  ", amount="5.00")]
    _, quarantine = vo.split_rows(rows, source_file="x.csv", loaded_at=RUN_TS)
    assert [r["reject_reason"] for r in quarantine] == ["missing_order_id", "missing_order_id"]


# --- TS-016: extra field ----------------------------------------------------


def test_ts016_extra_fields_go_to_quarantine_without_extras(tmp_path, dirs):
    src = tmp_path / "orders_extra.csv"
    good = ",".join(make_row("ORD-00001").values())
    extra = ",".join(make_row("ORD-00002").values()) + ",leftover1,leftover2"
    src.write_text(",".join(HEADER) + "\n" + good + "\n" + extra + "\n", encoding="utf-8")

    assert run_validator(src, dirs) == 0

    staging = read_output(dirs["staging"] / src.name)
    quarantine = read_output(dirs["quarantine"] / src.name)
    assert [r["order_id"] for r in staging] == ["ORD-00001"]
    assert len(quarantine) == 1
    assert quarantine[0]["reject_reason"] == "extra_fields:2"
    assert None not in quarantine[0]  # the output CSV keeps the right number of columns
    text = (dirs["quarantine"] / src.name).read_text(encoding="utf-8")
    assert "leftover" not in text
    assert vo.reason_counts(quarantine) == {"extra_fields": 1}
    assert all_files(dirs["staging"], dirs["quarantine"]) == [src.name, src.name]


def test_ts016_no_orphan_tmp_when_write_fails(tmp_path, dirs, monkeypatch, capsys):
    src = write_input(tmp_path / "orders_boom.csv", [make_row("ORD-00001")])
    real_write = vo._write_csv
    calls = {"n": 0}

    def failing_write(path, fieldnames, rows):
        calls["n"] += 1
        if calls["n"] == 2:  # fails halfway through writing the quarantine file
            path.write_text("partial", encoding="utf-8")
            raise OSError("disk full (simulated)")
        real_write(path, fieldnames, rows)

    monkeypatch.setattr(vo, "_write_csv", failing_write)

    assert run_validator(src, dirs) == 3

    assert all_files(dirs["staging"], dirs["quarantine"]) == []  # no orphan .tmp


# --- TS-017: unexpected error -----------------------------------------------


def test_ts017_unexpected_error_exits_3_without_traceback(tmp_path, dirs, monkeypatch, capsys):
    src = write_input(tmp_path / "orders_err.csv", [make_row("ORD-00001")])

    def boom(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(vo, "split_rows", boom)

    assert run_validator(src, dirs) == 3

    err = capsys.readouterr().err
    assert "unexpected error (RuntimeError); run with --debug for details" in err
    assert "simulated failure" not in err  # G-1: exception text only with --debug
    assert "Traceback" not in err
    assert all_files(dirs["staging"], dirs["quarantine"]) == []


def test_ts017_debug_flag_shows_traceback(tmp_path, dirs, monkeypatch, capsys):
    src = write_input(tmp_path / "orders_err.csv", [make_row("ORD-00001")])
    monkeypatch.setattr(vo, "split_rows", lambda *a, **k: 1 / 0)

    code = vo.main(
        [
            "--input", str(src), "--run-ts", RUN_TS,
            "--staging-dir", str(dirs["staging"]),
            "--quarantine-dir", str(dirs["quarantine"]),
            "--debug",
        ]
    )

    assert code == 3
    err = capsys.readouterr().err
    assert "Traceback" in err
    assert "ZeroDivisionError" in err


# --- TS-018: invalid directory flags ----------------------------------------


@pytest.mark.parametrize("case", ["same_dirs", "staging_is_input_dir", "quarantine_is_input_dir"])
def test_ts018_invalid_dir_flags_exit_2(tmp_path, case, capsys):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    src = write_input(raw_dir / "orders_k.csv", [make_row("ORD-00001")])
    original = src.read_bytes()
    other = tmp_path / "other"
    staging, quarantine = {
        "same_dirs": (other, other),
        "staging_is_input_dir": (raw_dir, other),
        "quarantine_is_input_dir": (other, raw_dir / "." ),
    }[case]

    assert run_validator(src, {"staging": staging, "quarantine": quarantine}) == 2

    assert "error:" in capsys.readouterr().err
    assert src.read_bytes() == original
    assert sorted(p.name for p in raw_dir.iterdir()) == ["orders_k.csv"]
    assert not other.exists()


# --- CLI --------------------------------------------------------------------


def test_cli_module_entrypoint(tmp_path, dirs):
    src = write_input(tmp_path / "orders_j.csv", [make_row("ORD-00001")])
    result = subprocess.run(
        [
            sys.executable, "-m", "ingestion.validate_orders",
            "--input", str(src),
            "--run-ts", RUN_TS,
            "--staging-dir", str(dirs["staging"]),
            "--quarantine-dir", str(dirs["quarantine"]),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (dirs["staging"] / "orders_j.csv").is_file()


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ingestion.validate_orders", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


# --- F2: invalid bytes and unreadable CSV ----------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        # Valid header followed by bytes that are not UTF-8.
        (",".join(HEADER) + "\nORD-00001,ORG-001").encode("utf-8") + b"\xff\xfe,x\n",
        # Invalid byte right at the start.
        b"\xff" + ",".join(HEADER).encode("utf-8") + b"\n",
    ],
    ids=["invalid_utf8_in_body", "invalid_utf8_in_header"],
)
def test_f2_invalid_utf8_exits_2_without_outputs(tmp_path, dirs, capsys, payload):
    src = tmp_path / "orders_bin.csv"
    src.write_bytes(payload)

    assert run_validator(src, dirs) == 2

    captured = capsys.readouterr()
    assert "is not valid UTF-8" in captured.err
    assert "orders_bin.csv" in captured.err
    assert str(tmp_path) not in captured.err
    assert captured.out == ""  # no partial summary
    assert not dirs["staging"].exists()
    assert not dirs["quarantine"].exists()


def test_f2_unreadable_csv_exits_2_without_outputs(tmp_path, dirs, capsys):
    """Field above ``csv.field_size_limit()``: the csv module raises ``csv.Error``."""
    src = tmp_path / "orders_huge.csv"
    row = ",".join(make_row("ORD-00001").values())
    huge = "X" * (csv.field_size_limit() + 1)
    src.write_text(",".join(HEADER) + "\n" + row + "\n" + huge + "\n", encoding="utf-8")

    assert run_validator(src, dirs) == 2

    captured = capsys.readouterr()
    assert "is not a readable CSV" in captured.err
    assert "orders_huge.csv" in captured.err
    assert "XXXX" not in captured.err  # row content does not leak
    assert captured.out == ""
    assert not dirs["staging"].exists()
    assert not dirs["quarantine"].exists()


def test_f2_invalid_input_keeps_previous_outputs(tmp_path, dirs):
    src = write_input(tmp_path / "orders_keep.csv", [make_row("ORD-00001")])
    assert run_validator(src, dirs) == 0
    before = (dirs["staging"] / src.name).read_bytes()

    src.write_bytes(b"\xff\xfe\x00")
    assert run_validator(src, dirs) == 2

    assert (dirs["staging"] / src.name).read_bytes() == before
    assert all_files(dirs["staging"], dirs["quarantine"]) == [src.name, src.name]  # no .tmp


# --- G-1: unexpected error without exception text ---------------------------


def test_g1_cli_unexpected_error_hides_exception_text(tmp_path):
    """Real error (staging dir is a file): the OSError text contains the path."""
    src = write_input(tmp_path / "orders_g1.csv", [make_row("ORD-00001")])
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    args = (
        "--input", str(src), "--run-ts", RUN_TS,
        "--staging-dir", str(blocker), "--quarantine-dir", str(tmp_path / "q"),
    )

    result = run_cli(*args)

    assert result.returncode == 3
    assert "unexpected error (" in result.stderr
    assert "Traceback" not in result.stderr
    assert str(tmp_path) not in result.stderr
    assert "blocker" not in result.stderr
    assert not (tmp_path / "q").exists() or list((tmp_path / "q").iterdir()) == []

    debug = run_cli(*args, "--debug")

    assert debug.returncode == 3
    assert "Traceback" in debug.stderr


# --- G-2: messages show only the file name -----------------------------------


def test_g2_missing_input_message_shows_only_file_name(tmp_path, dirs, capsys):
    missing = tmp_path / "sub" / "orders_gone.csv"

    assert run_validator(missing, dirs) == 2

    err = capsys.readouterr().err
    assert "orders_gone.csv" in err
    assert str(tmp_path) not in err
    assert str(missing.parent) not in err


def test_g2_cli_messages_never_show_absolute_path(tmp_path):
    src = write_input(tmp_path / "orders_g2.csv", [make_row("ORD-00001")], header=HEADER[1:])
    cases = [
        ("--input", str(tmp_path / "does_not_exist.csv")),
        ("--input", str(src)),  # incomplete header
    ]
    for input_args in cases:
        result = run_cli(
            *input_args, "--run-ts", RUN_TS,
            "--staging-dir", str(tmp_path / "s"), "--quarantine-dir", str(tmp_path / "q"),
        )
        assert result.returncode == 2
        assert result.stderr.startswith("error: ")
        assert str(tmp_path) not in result.stderr
        assert str(tmp_path) not in result.stdout


# --- T-026: --debug help warns that it is unsafe -----------------------------


def test_debug_help_warns_it_is_unsafe():
    result = run_cli("--help")
    assert result.returncode == 0
    help_text = " ".join(result.stdout.split())  # argparse wraps long help lines
    assert "Unsafe: may expose paths and values; never enable in a DAG/production." in help_text
