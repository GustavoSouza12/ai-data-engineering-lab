"""RAW load into local DuckDB (MVP-06, TS-030).

The sample runs through the real validator into a temporary folder; the other inputs
are fictitious and built inside the test itself. Every DuckDB file is temporary.
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import duckdb
import pytest

from ingestion import load_raw as lr
from ingestion import validate_orders as vo

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_RAW = REPO_ROOT / "data" / "raw" / "orders" / "orders_2026-11-19.csv"
SAMPLE_NAME = SAMPLE_RAW.name
DAY2_NAME = "orders_2026-11-20.csv"
RUN_TS = "2026-11-19T03:00:00Z"
DAY2_RUN_TS = "2026-11-20T03:00:00Z"


@pytest.fixture
def dirs(tmp_path: Path) -> dict[str, Path]:
    return {
        "staging": tmp_path / "staging",
        "quarantine": tmp_path / "quarantine",
        "database": tmp_path / "db" / "lab_test.duckdb",
    }


def validate(raw: Path, dirs: dict[str, Path], run_ts: str = RUN_TS) -> None:
    code = vo.run(raw, run_ts, staging_dir=dirs["staging"], quarantine_dir=dirs["quarantine"])
    assert code == vo.EXIT_OK


def load_cli(dirs: dict[str, Path], source_file: str = SAMPLE_NAME) -> int:
    return lr.main(
        [
            "--source-file", source_file,
            "--staging-dir", str(dirs["staging"]),
            "--quarantine-dir", str(dirs["quarantine"]),
            "--database", str(dirs["database"]),
        ]
    )


def counts(database: Path) -> dict[tuple[str, str], int]:
    """(table, _source_file) -> rows, for both RAW tables."""
    with duckdb.connect(str(database), read_only=True) as con:
        rows = con.execute(
            "select 'orders', _source_file, count(*) from raw.orders group by all"
            " union all"
            " select 'orders_quarantine', _source_file, count(*)"
            " from raw.orders_quarantine group by all"
        ).fetchall()
    return {(table, source): n for table, source, n in rows}


def table_rows(database: Path, table: str) -> list[tuple]:
    with duckdb.connect(str(database), read_only=True) as con:
        return sorted(con.execute(f"select * from raw.{table}").fetchall())


def csv_rows(path: Path, columns: tuple[str, ...]) -> list[tuple]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return sorted(tuple(row[c] for c in columns) for row in csv.DictReader(fh))


def make_day2(tmp_path: Path, dirs: dict[str, Path]) -> None:
    """A second daily file: the sample under another name and run timestamp."""
    raw = tmp_path / "raw" / DAY2_NAME
    raw.parent.mkdir(parents=True)
    shutil.copyfile(SAMPLE_RAW, raw)
    validate(raw, dirs, DAY2_RUN_TS)


SAMPLE_COUNTS = {("orders", SAMPLE_NAME): 272, ("orders_quarantine", SAMPLE_NAME): 12}


@pytest.fixture
def loaded(dirs: dict[str, Path]) -> dict[str, Path]:
    """The sample validated and loaded once."""
    validate(SAMPLE_RAW, dirs)
    assert load_cli(dirs) == lr.EXIT_OK
    return dirs


# --- Load and idempotency --------------------------------------------------


def test_sample_loads_272_and_12(dirs, capsys):
    validate(SAMPLE_RAW, dirs)
    capsys.readouterr()

    assert load_cli(dirs) == lr.EXIT_OK

    assert counts(dirs["database"]) == SAMPLE_COUNTS
    out = capsys.readouterr().out
    assert "raw.orders:            272 loaded (file 272, replaced 0)" in out
    assert "reconciliation: OK" in out


def test_columns_are_text_as_received_plus_metadata(loaded):
    with duckdb.connect(str(loaded["database"]), read_only=True) as con:
        for target in (lr.ORDERS, lr.QUARANTINE):
            columns = con.execute(
                "select column_name, data_type from information_schema.columns"
                " where table_schema = 'raw' and table_name = ? order by ordinal_position",
                [target.table],
            ).fetchall()
            assert columns == [(c, "VARCHAR") for c in target.columns]
    # Values are byte-for-byte what the validator wrote, untrimmed (whitespace-only fields
    # of the quarantine included).
    assert table_rows(loaded["database"], "orders") == csv_rows(
        loaded["staging"] / SAMPLE_NAME, lr.ORDERS_COLUMNS
    )
    assert table_rows(loaded["database"], "orders_quarantine") == csv_rows(
        loaded["quarantine"] / SAMPLE_NAME, lr.QUARANTINE_COLUMNS
    )
    loaded_at = {r[lr.ORDERS_COLUMNS.index("_loaded_at")] for r in table_rows(
        loaded["database"], "orders"
    )}
    assert loaded_at == {"2026-11-19T03:00:00Z"}


def test_rerun_same_file_gives_same_counts_and_rows(loaded, capsys):
    before = table_rows(loaded["database"], "orders"), table_rows(
        loaded["database"], "orders_quarantine"
    )
    capsys.readouterr()

    assert load_cli(loaded) == lr.EXIT_OK

    assert counts(loaded["database"]) == SAMPLE_COUNTS
    after = table_rows(loaded["database"], "orders"), table_rows(
        loaded["database"], "orders_quarantine"
    )
    assert after == before
    out = capsys.readouterr().out
    assert "raw.orders:            272 loaded (file 272, replaced 272)" in out
    assert "raw.orders_quarantine: 12 loaded (file 12, replaced 12)" in out


def test_two_days_coexist_and_a_rerun_touches_only_its_day(loaded, tmp_path):
    make_day2(tmp_path, loaded)
    assert load_cli(loaded, DAY2_NAME) == lr.EXIT_OK
    both = {
        **SAMPLE_COUNTS,
        ("orders", DAY2_NAME): 272,
        ("orders_quarantine", DAY2_NAME): 12,
    }
    assert counts(loaded["database"]) == both

    assert load_cli(loaded) == lr.EXIT_OK
    assert counts(loaded["database"]) == both


def test_rerun_after_the_file_changed_replaces_the_day(loaded):
    # The same day is validated again with fewer rows: the old rows must not linger.
    staging = loaded["staging"] / SAMPLE_NAME
    lines = staging.read_text(encoding="utf-8").splitlines(keepends=True)
    staging.write_text("".join(lines[:11]), encoding="utf-8")

    assert load_cli(loaded) == lr.EXIT_OK
    assert counts(loaded["database"]) == {
        ("orders", SAMPLE_NAME): 10,
        ("orders_quarantine", SAMPLE_NAME): 12,
    }


def test_header_only_files_load_zero_rows(tmp_path, dirs):
    raw = tmp_path / "orders_2026-11-21.csv"
    raw.write_text(",".join(vo.REQUIRED_COLUMNS) + "\n", encoding="utf-8")
    validate(raw, dirs)

    assert load_cli(dirs, raw.name) == lr.EXIT_OK
    assert counts(dirs["database"]) == {}
    assert table_rows(dirs["database"], "orders") == []


# --- Atomicity: nothing is ever partially loaded ---------------------------


def test_failure_mid_transaction_leaves_raw_unchanged(loaded, tmp_path, monkeypatch, capsys):
    make_day2(tmp_path, loaded)
    assert load_cli(loaded, DAY2_NAME) == lr.EXIT_OK
    before = counts(loaded["database"])
    snapshot = table_rows(loaded["database"], "orders")
    real_insert = lr._insert_rows

    def insert_then_fail(con, target, rows):
        # raw.orders was already deleted and reinserted; die before the quarantine.
        if target is lr.QUARANTINE:
            raise RuntimeError("simulated crash ORD-00001")
        real_insert(con, target, rows)

    monkeypatch.setattr(lr, "_insert_rows", insert_then_fail)
    capsys.readouterr()

    assert load_cli(loaded) == lr.EXIT_UNEXPECTED_ERROR

    assert counts(loaded["database"]) == before
    assert table_rows(loaded["database"], "orders") == snapshot
    err = capsys.readouterr().err
    assert "unexpected error (RuntimeError)" in err
    assert "ORD-" not in err


def test_failure_on_the_first_load_creates_nothing(tmp_path, dirs, monkeypatch):
    validate(SAMPLE_RAW, dirs)

    def fail(con, target, rows):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(lr, "_insert_rows", fail)

    assert load_cli(dirs) == lr.EXIT_UNEXPECTED_ERROR
    with duckdb.connect(str(dirs["database"]), read_only=True) as con:
        tables = con.execute(
            "select table_name from information_schema.tables where table_schema = 'raw'"
        ).fetchall()
    assert tables == []


def test_reconciliation_mismatch_rolls_back_with_exit_1(loaded, monkeypatch, capsys):
    before = counts(loaded["database"])
    real_insert = lr._insert_rows

    def drop_last_quarantine_row(con, target, rows):
        real_insert(con, target, rows[:-1] if target is lr.QUARANTINE else rows)

    monkeypatch.setattr(lr, "_insert_rows", drop_last_quarantine_row)
    capsys.readouterr()

    assert load_cli(loaded) == lr.EXIT_RECONCILIATION_FAILED

    assert counts(loaded["database"]) == before
    captured = capsys.readouterr()
    assert "reconciliation: FAILED" in captured.out
    assert "file 12 = raw.orders_quarantine 11" in captured.out
    assert "rolled back" in captured.err


def test_load_result_reconciles_only_when_every_target_matches():
    ok = lr.TargetResult(lr.ORDERS, file_rows=3, replaced_rows=0, loaded_rows=3)
    short = lr.TargetResult(lr.QUARANTINE, file_rows=2, replaced_rows=0, loaded_rows=1)
    assert lr.LoadResult("orders_x.csv", (ok,)).reconciled
    assert not lr.LoadResult("orders_x.csv", (ok, short)).reconciled


# --- Invalid input: exit 2, RAW untouched ----------------------------------


@pytest.mark.parametrize(
    "name", ["../orders_2026-11-19.csv", "sub/orders_2026-11-19.csv", "orders.txt", "", ".."]
)
def test_source_file_must_be_a_csv_file_name(dirs, capsys, name):
    assert load_cli(dirs, name) == lr.EXIT_INVALID_INPUT
    assert "error: --source-file" in capsys.readouterr().err
    assert not dirs["database"].exists()


def test_missing_quarantine_file_exits_2_without_creating_the_database(dirs, capsys):
    validate(SAMPLE_RAW, dirs)
    (dirs["quarantine"] / SAMPLE_NAME).unlink()

    assert load_cli(dirs) == lr.EXIT_INVALID_INPUT
    assert f"orders_quarantine input not found: {SAMPLE_NAME}" in capsys.readouterr().err
    assert not dirs["database"].exists()


def _rewrite(path: Path, edit) -> None:
    with path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    rows = edit(rows)
    with path.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerows(rows)


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda rows: [r[:-1] for r in rows], "does not have the columns of raw.orders"),
        (lambda rows: [rows[0] + ["extra"]] + [r + ["x"] for r in rows[1:]],
         "does not have the columns of raw.orders"),
        (lambda rows: [rows[0] + [rows[0][0]]] + [r + [r[0]] for r in rows[1:]],
         "does not have the columns of raw.orders"),
        (lambda rows: rows[:2] + [rows[2] + ["x"]] + rows[3:], "line 3: wrong number of fields"),
        (lambda rows: rows[:2] + [rows[2][:-1]] + rows[3:], "line 3: wrong number of fields"),
        (lambda rows: rows[:2] + [rows[2][:-2] + ["orders_other.csv", rows[2][-1]]] + rows[3:],
         f"line 3: _source_file is not {SAMPLE_NAME}"),
    ],
    ids=["missing-column", "off-contract-column", "duplicate-column", "extra-field",
         "missing-field", "other-source-file"],
)
def test_unexpected_staging_file_exits_2_and_keeps_raw(loaded, capsys, edit, message):
    before = counts(loaded["database"])
    _rewrite(loaded["staging"] / SAMPLE_NAME, edit)
    capsys.readouterr()

    assert load_cli(loaded) == lr.EXIT_INVALID_INPUT

    err = capsys.readouterr().err
    assert message in err
    assert "ORD-" not in err
    assert counts(loaded["database"]) == before


def test_raw_table_that_drifted_exits_2_and_keeps_raw(loaded, capsys):
    with duckdb.connect(str(loaded["database"])) as con:
        con.execute("alter table raw.orders_quarantine add column note varchar")
    before = counts(loaded["database"])
    capsys.readouterr()

    assert load_cli(loaded) == lr.EXIT_INVALID_INPUT

    assert "raw.orders_quarantine has columns that differ" in capsys.readouterr().err
    assert counts(loaded["database"]) == before


def test_output_never_carries_row_values_or_paths(loaded, capsys, tmp_path):
    assert load_cli(loaded) == lr.EXIT_OK
    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert "ORD-" not in text
    assert "ORG-" not in text
    assert str(tmp_path) not in text


def test_create_table_sql_keeps_contract_order_and_text_types():
    sql = lr.create_table_sql(lr.QUARANTINE)
    assert sql.startswith("CREATE TABLE IF NOT EXISTS raw.orders_quarantine")
    positions = [sql.index(f"    {c} VARCHAR") for c in lr.QUARANTINE_COLUMNS]
    assert positions == sorted(positions)
    assert "_source_file VARCHAR NOT NULL" in sql
    assert "reject_reason VARCHAR NOT NULL" in sql
    assert "order_id VARCHAR," in sql
