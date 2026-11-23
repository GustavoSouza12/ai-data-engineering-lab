"""Generator by logical date (MVP-05): determinism and the content of daily files."""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from itertools import islice
from pathlib import Path

import pytest

from ingestion import generate_orders as go
from ingestion import validate_orders as vo

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "data" / "raw" / "orders" / "orders_2026-11-19.csv"
N_CHECKED_DAYS = 5  # base file plus 4 daily files
RUN_TS = "2026-11-21T08:00:00Z"


def _key(r: dict) -> tuple[str, str]:
    return r["order_id"], r["updated_at"]


def _content(r: dict) -> tuple[str, ...]:
    return tuple(r[c] for c in vo.REQUIRED_COLUMNS)


def _read(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def files() -> list[tuple[date, list[dict]]]:
    return list(islice(go.iter_daily_files(), N_CHECKED_DAYS))


@pytest.fixture(scope="module")
def conflict_files() -> list[tuple[date, list[dict]]]:
    """The same chain with --plant-cross-file-conflict."""
    return list(islice(go.iter_daily_files(plant_cross_file_conflict=True), N_CHECKED_DAYS))


@pytest.fixture(params=["default", "with_conflict"])
def any_files(request, files, conflict_files):
    return files if request.param == "default" else conflict_files


@pytest.fixture(scope="module")
def planted_ids() -> set[str]:
    return go._generate_base(go.SEED)[1]


def _daily(files):
    """(file_date, rows, every earlier row, rows of the previous file) for each daily file."""
    for i in range(1, len(files)):
        earlier = [r for _, rows in files[:i] for r in rows]
        yield files[i][0], files[i][1], earlier, files[i - 1][1]


# Determinism and the base sample ---------------------------------------------------------


def test_default_date_is_byte_identical_to_sample(tmp_path):
    assert go.main(["--output-dir", str(tmp_path)]) == 0
    assert (tmp_path / SAMPLE.name).read_bytes() == SAMPLE.read_bytes()


def test_base_date_is_byte_identical_to_sample(tmp_path):
    out = tmp_path / "x.csv"
    assert go.main(["--date", "2026-11-19", "--output", str(out)]) == 0
    assert out.read_bytes() == SAMPLE.read_bytes()


def test_same_date_same_bytes(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert go.main(["--date", "2026-11-22", "--output-dir", str(a)]) == 0
    # Written as part of a multi-day run: the bytes do not depend on how it is called.
    assert go.main(["--date", "2026-11-20", "--days", "3", "--output-dir", str(b)]) == 0
    name = "orders_2026-11-22.csv"
    assert (a / name).read_bytes() == (b / name).read_bytes()
    assert sorted(p.name for p in b.iterdir()) == [
        "orders_2026-11-20.csv",
        "orders_2026-11-21.csv",
        "orders_2026-11-22.csv",
    ]
    assert (b / "orders_2026-11-20.csv").read_bytes() != (b / name).read_bytes()


def test_flag_does_not_change_the_base_sample(tmp_path):
    assert go.main(["--output-dir", str(tmp_path), "--plant-cross-file-conflict"]) == 0
    assert (tmp_path / SAMPLE.name).read_bytes() == SAMPLE.read_bytes()


def test_same_date_same_bytes_with_the_flag(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    flag = "--plant-cross-file-conflict"
    assert go.main(["--date", "2026-11-22", "--output-dir", str(a), flag]) == 0
    assert go.main(["--date", "2026-11-20", "--days", "3", "--output-dir", str(b), flag]) == 0
    name = "orders_2026-11-22.csv"
    assert (a / name).read_bytes() == (b / name).read_bytes()


def test_seed_is_derived_from_the_date():
    assert go.day_seed(go.BASE_DATE) == go.SEED
    assert go.day_seed(date(2026, 11, 20)) == go.SEED + 1
    assert go.day_seed(date(2026, 11, 20), seed=7) == 8


def test_generate_orders_for_date(files, conflict_files):
    assert go.generate_orders_for_date(go.BASE_DATE) == go.generate_orders(go.SEED)
    assert go.generate_orders_for_date(files[3][0]) == files[3][1]
    planted = go.generate_orders_for_date(files[3][0], plant_cross_file_conflict=True)
    assert planted == conflict_files[3][1]
    with pytest.raises(ValueError):
        go.generate_orders_for_date(date(2026, 11, 18))


@pytest.mark.parametrize(
    "argv",
    [
        ["--date", "2026-11-18"],
        ["--date", "2026-11-31"],
        ["--date", "20261120"],
        ["--date", "2026-11-20", "--days", "0"],
        ["--date", "2026-11-20", "--days", "2", "--output", "x.csv"],
    ],
)
def test_cli_rejects_invalid_arguments(argv, tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        go.main([*argv, "--output-dir", str(tmp_path)])
    assert exc.value.code == 2
    assert list(tmp_path.iterdir()) == []


# Content of the daily files --------------------------------------------------------------


def test_daily_files_have_the_documented_counts(files, conflict_files):
    for _, rows, _, _ in _daily(conflict_files):
        assert len(rows) == go.N_DAILY_ROWS_WITH_CONFLICT
    for file_date, rows, earlier, _ in _daily(files):
        assert len(rows) == go.N_DAILY_ROWS
        assert list(rows[0]) == list(vo.REQUIRED_COLUMNS)
        new_ids = {r["order_id"] for r in rows} - {r["order_id"] for r in earlier}
        first = go.first_order_number(file_date)
        assert new_ids == {f"ORD-{n:05d}" for n in range(first, first + go.N_DAILY_NEW_ORDERS)}
        assert rows == sorted(rows, key=lambda r: (r["updated_at"], r["order_id"]))


def test_daily_new_orders(any_files):
    for file_date, rows, earlier, _ in _daily(any_files):
        seen = {r["order_id"] for r in earlier}
        new = [r for r in rows if r["order_id"] not in seen]
        assert len(new) == go.N_DAILY_NEW_ORDERS
        for r in new:
            assert r["status"] == "submitted"
            assert r["submitted_at"] == r["updated_at"]
            assert r["updated_at"][:10] == file_date.isoformat()


def test_daily_new_versions_of_previous_file_orders(any_files):
    for file_date, rows, earlier, previous in _daily(any_files):
        earlier_keys = {_key(r) for r in earlier}
        previous_ids = {r["order_id"] for r in previous}
        on_day = [
            r
            for r in rows
            if r["order_id"] in previous_ids
            and _key(r) not in earlier_keys
            and r["updated_at"][:10] == file_date.isoformat()
        ]
        assert len(on_day) == go.N_DAILY_UPDATES
        for r in on_day:
            history = sorted(
                (e for e in earlier if e["order_id"] == r["order_id"]),
                key=lambda e: e["updated_at"],
            )
            last = history[-1]
            assert r["updated_at"] > last["updated_at"]
            assert r["status"] in go.NEXT_STATUSES[last["status"]]
            assert (r["submitted_at"], r["investor_id"]) == (
                last["submitted_at"],
                last["investor_id"],
            )


def test_daily_late_version(any_files):
    for file_date, rows, earlier, _ in _daily(any_files):
        earlier_keys = {_key(r) for r in earlier}
        file_start = datetime.combine(file_date, datetime.min.time())
        late = [
            r
            for r in rows
            if _key(r) not in earlier_keys
            and datetime.fromisoformat(r["updated_at"]) < file_start - timedelta(days=1)
        ]
        assert len(late) == go.N_DAILY_LATE_VERSIONS
        for r in late:
            # More than 1 day before the file date, inside the 3-day lookback (ADR-0010).
            assert file_start - timedelta(days=3) <= datetime.fromisoformat(r["updated_at"])
            history = [e for e in earlier if e["order_id"] == r["order_id"]]
            assert history  # a new version of a known order, not a new order
            assert r["updated_at"] > max(e["updated_at"] for e in history)


def test_default_daily_files_have_no_cross_file_conflict(files):
    # Default runs repeat no version key of an earlier file (ADR-0009, amendment 2026-11-23).
    for _, rows, earlier, _ in _daily(files):
        earlier_keys = {_key(r) for r in earlier}
        assert not [r for r in rows if _key(r) in earlier_keys]
        assert len({_key(r) for r in rows}) == len(rows)


def test_flag_adds_one_row_to_the_first_daily_file(files, conflict_files):
    # Same rng draws up to the conflict, which is the last step of a daily file. Later files
    # differ because the conflicted order is frozen.
    default_rows, planted_rows = files[1][1], conflict_files[1][1]
    default_keys = {_key(r) for r in default_rows}
    extra = [r for r in planted_rows if r not in default_rows]
    assert [r for r in planted_rows if r in default_rows] == default_rows
    assert len(extra) == go.N_DAILY_CROSS_FILE_CONFLICTS
    assert not {_key(r) for r in extra} & default_keys


def test_daily_cross_file_conflict_with_the_flag(conflict_files):
    for _, rows, earlier, previous in _daily(conflict_files):
        previous_by_key = {_key(r): r for r in previous}
        earlier_keys = {_key(r) for r in earlier}
        repeated = [r for r in rows if _key(r) in earlier_keys]
        # The only repeated version key is the conflict, and it comes from the previous file.
        assert len(repeated) == go.N_DAILY_CROSS_FILE_CONFLICTS
        for r in repeated:
            original = previous_by_key[_key(r)]
            assert _content(r) != _content(original)
            assert {c for c in vo.REQUIRED_COLUMNS if r[c] != original[c]} == {"amount"}
        assert len({_key(r) for r in rows}) == len(rows)  # no conflict inside the file


def test_daily_files_leave_planted_orders_and_conflicts_alone(any_files, planted_ids):
    frozen = set(planted_ids)
    for _, rows, earlier, _ in _daily(any_files):
        earlier_keys = {_key(r) for r in earlier}
        assert not {r["order_id"] for r in rows} & frozen
        frozen |= {r["order_id"] for r in rows if _key(r) in earlier_keys}


def test_daily_files_are_semantically_clean(any_files):
    # The 3 planted semantic errors of the base file stay the only ones (ADR-0017, T3).
    for file_date, rows, _, _ in _daily(any_files):
        file_end = datetime.combine(file_date, datetime.max.time()).isoformat(timespec="seconds")
        for r in rows:
            assert all(r[c].strip() == r[c] != "" for c in vo.REQUIRED_COLUMNS)
            assert float(r["amount"]) > 0
            assert r["channel"] in go.CHANNELS
            assert r["currency"] in go.CURRENCIES
            assert r["status"] in go.STATUSES
            assert r["submitted_at"] <= r["updated_at"] <= file_end
            assert 1 <= int(r["organization_id"][4:]) <= go.N_ORGANIZATIONS_WITH_ORDERS


def test_ingestion_does_not_see_the_cross_file_conflict(tmp_path):
    # Detecting it is the job of dbt across files (MVP-02, ADR-0009 amendment), not of the
    # validator, which sees one file at a time.
    raw = tmp_path / "raw"
    argv = ["--date", "2026-11-20", "--output-dir", str(raw), "--plant-cross-file-conflict"]
    assert go.main(argv) == 0
    name = "orders_2026-11-20.csv"
    code = vo.run(raw / name, RUN_TS, tmp_path / "staging", tmp_path / "quarantine")
    assert code == 0
    assert len(_read(tmp_path / "staging" / name)) == go.N_DAILY_ROWS_WITH_CONFLICT
    assert _read(tmp_path / "quarantine" / name) == []
