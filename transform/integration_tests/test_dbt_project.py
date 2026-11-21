"""Integration tests for the dbt-duckdb project (F0.2a, MVP-02: TS-025, TS-026; MVP-06).

Each scenario runs the real validator on raw CSVs into temporary staging and
quarantine folders, the real RAW loader into a temporary DuckDB file, then
``dbt build`` on that same file, with dbt's target and log folders also under
the temporary directory. Nothing is written to the worktree.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_DIR = REPO_ROOT / "transform"
SAMPLE_RAW = REPO_ROOT / "data" / "raw" / "orders" / "orders_2026-11-19.csv"
CROSS_FILE_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cross_file_conflict"
RUN_TS = "2026-11-19T03:00:00Z"
AUDIT_SCHEMA = "main_dbt_test__audit"

SEMANTIC_TESTS = {
    "ts009_fct_orders_channel_accepted": "ORD-00047",
    "ts010_fct_orders_amount_castable_and_positive": "ORD-00123",
    "ts012_fct_orders_timestamps_within_file_date": "ORD-00084",
}
SEMANTIC_TESTS_THAT_PASS = (
    "ts009_fct_orders_currency_accepted",
    "ts009_fct_orders_status_accepted",
)
CONFLICT_TEST = "assert_no_cross_file_conflicting_versions"
GOVERNED_RESOURCE_TYPES = ("model", "seed")
PII_LEVELS = {"restricted", "confidential", "internal", "public"}


@dataclass
class Build:
    success: bool
    statuses: dict[str, str]  # test or node name -> status
    database: Path
    target_dir: Path

    def query(self, sql: str) -> list[tuple]:
        with duckdb.connect(str(self.database), read_only=True) as con:
            return con.execute(sql).fetchall()


def _validate_and_load(
    raw_files: list[Path], staging_dir: Path, quarantine_dir: Path, database: Path
) -> None:
    dirs = ["--staging-dir", str(staging_dir), "--quarantine-dir", str(quarantine_dir)]
    for raw in raw_files:
        for step in (
            ["ingestion.validate_orders", "--input", str(raw), "--run-ts", RUN_TS],
            ["ingestion.load_raw", "--source-file", raw.name, "--database", str(database)],
        ):
            subprocess.run(
                [sys.executable, "-m", *step, *dirs],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
            )


def _build(tmp: Path, raw_files: list[Path]) -> Build:
    database = tmp / "lab_test.duckdb"
    _validate_and_load(raw_files, tmp / "staging", tmp / "quarantine", database)
    target_dir = tmp / "target"
    # A subprocess, not dbtRunner: dbt-duckdb keeps its connection open in the
    # calling process, which would block the read-only connections below.
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "dbt.cli.main",
            "build",
            "--project-dir",
            str(PROJECT_DIR),
            "--profiles-dir",
            str(PROJECT_DIR),
            "--target-path",
            str(target_dir),
            "--log-path",
            str(tmp / "logs"),
        ],
        cwd=PROJECT_DIR,
        env={**os.environ, "LAB_DUCKDB_PATH": str(database)},
        capture_output=True,
        text=True,
    )
    assert completed.returncode in (0, 1), completed.stdout + completed.stderr
    run_results = json.loads((target_dir / "run_results.json").read_text())
    statuses = {r["unique_id"].split(".")[2]: r["status"] for r in run_results["results"]}
    return Build(completed.returncode == 0, statuses, database, target_dir)


@pytest.fixture(scope="module")
def sample_build(tmp_path_factory: pytest.TempPathFactory) -> Build:
    return _build(tmp_path_factory.mktemp("sample"), [SAMPLE_RAW])


@pytest.fixture(scope="module")
def conflict_build(tmp_path_factory: pytest.TempPathFactory) -> Build:
    raw_files = sorted(CROSS_FILE_FIXTURE.glob("orders_*.csv"))
    assert len(raw_files) == 2
    return _build(tmp_path_factory.mktemp("conflict"), raw_files)


# ---------------------------------------------------------------------------
# Sample: data/raw/orders/orders_2026-11-19.csv
# ---------------------------------------------------------------------------


def test_sample_build_succeeds_with_exactly_the_three_semantic_warnings(sample_build: Build):
    assert sample_build.success
    counts = Counter(sample_build.statuses.values())
    assert counts["warn"] == 3
    assert counts["error"] == 0
    assert counts["fail"] == 0
    assert counts["skipped"] == 0
    warned = {name for name, status in sample_build.statuses.items() if status == "warn"}
    assert warned == set(SEMANTIC_TESTS)
    for name in SEMANTIC_TESTS_THAT_PASS:
        assert sample_build.statuses[name] == "pass"


@pytest.mark.parametrize(("test_name", "order_id"), sorted(SEMANTIC_TESTS.items()))
def test_semantic_tests_store_exactly_the_planted_order(
    sample_build: Build, test_name: str, order_id: str
):
    rows = sample_build.query(f'select order_id from {AUDIT_SCHEMA}."{test_name}"')
    assert rows == [(order_id,)]


def test_planted_semantic_errors_stay_in_gold(sample_build: Build):
    rows = sample_build.query(
        "select order_id from main.fct_orders"
        " where order_id in ('ORD-00047', 'ORD-00123', 'ORD-00084') order by order_id"
    )
    assert rows == [("ORD-00047",), ("ORD-00084",), ("ORD-00123",)]


def test_raw_layer_holds_the_sample_as_received(sample_build: Build):
    rows = sample_build.query(
        "select (select count(*) from raw.orders), (select count(*) from raw.orders_quarantine)"
    )
    assert rows == [(272, 12)]


def test_stg_orders_trims_before_deduplicating(sample_build: Build):
    # 272 validated rows, of which 2 are exact duplicates.
    assert sample_build.query("select count(*) from main.stg_orders") == [(270,)]


def test_int_orders__latest_keeps_one_row_per_order(sample_build: Build):
    rows = sample_build.query(
        "select count(*), count(distinct order_id) from main.int_orders__latest"
    )
    assert rows == [(190, 190)]
    assert sample_build.statuses["assert_int_orders__latest_is_latest_version"] == "pass"


def test_fct_orders_grain_and_amount_usd(sample_build: Build):
    assert sample_build.query("select count(*), count(distinct order_id) from main.fct_orders") == [
        (190, 190)
    ]
    rows = sample_build.query(
        "select o.amount, o.amount_usd, r.rate_to_usd"
        " from main.fct_orders o join main.fx_rates r"
        " on r.currency = o.currency and r.rate_date = cast(o.submitted_at as date)"
    )
    assert len(rows) == 190
    for amount, amount_usd, rate in rows:
        assert amount_usd == (amount * rate).quantize(Decimal("0.01"))


def test_fx_rates_cover_every_sample_date_and_currency(sample_build: Build):
    rows = sample_build.query(
        "select min(rate_date)::varchar, max(rate_date)::varchar, count(*),"
        " count(distinct currency) from main.fx_rates"
    )
    assert rows == [("2026-11-01", "2026-11-12", 36, 3)]
    assert sample_build.statuses["assert_every_order_has_fx_rate"] == "pass"


def test_reconciliation_and_relationship_tests_pass(sample_build: Build):
    for name in (
        "assert_orders_reconcile_latest_to_gold",
        "ts020_fct_orders_organization_exists",
        "assert_org_summary_reconciles_with_gold",
        CONFLICT_TEST,
    ):
        assert sample_build.statuses[name] == "pass", name


def test_org_summary_keeps_organizations_without_orders(sample_build: Build):
    assert sample_build.query("select count(*) from main.org_summary") == [(20,)]
    empty = sample_build.query(
        "select organization_id from main.org_summary"
        " where order_count = 0 and total_amount_usd = 0 order by organization_id"
    )
    assert empty == [(f"ORG-{n:03d}",) for n in range(16, 21)]
    totals = sample_build.query(
        "select (select sum(total_amount_usd) from main.org_summary),"
        " (select sum(amount_usd) from main.fct_orders),"
        " (select sum(order_count) from main.org_summary)"
    )
    summary_usd, gold_usd, n_orders = totals[0]
    assert summary_usd == gold_usd
    assert n_orders == 190


def test_every_column_has_pii_level_and_gold_has_owner(sample_build: Build):
    manifest = json.loads((sample_build.target_dir / "manifest.json").read_text())
    nodes = [
        node
        for node in manifest["nodes"].values()
        if node["resource_type"] in GOVERNED_RESOURCE_TYPES
    ]
    nodes += list(manifest["sources"].values())
    assert nodes
    with duckdb.connect(str(sample_build.database), read_only=True) as con:
        for node in nodes:
            documented = node["columns"]
            if node["resource_type"] != "source":
                actual = {
                    row[0]
                    for row in con.execute(
                        "select column_name from information_schema.columns"
                        " where table_schema = ? and table_name = ?",
                        [node["schema"], node["alias"]],
                    ).fetchall()
                }
                assert actual == set(documented), node["name"]
            for column in documented.values():
                assert column["meta"].get("pii_level") in PII_LEVELS, (
                    node["name"],
                    column["name"],
                )
            if node["resource_type"] == "model" and node["fqn"][1] in ("gold", "marts"):
                assert node["description"], node["name"]
                assert node["config"]["meta"].get("owner"), node["name"]
                assert all(c["description"] for c in documented.values()), node["name"]
    amount_levels = {
        node["columns"]["amount"]["meta"]["pii_level"]
        for node in nodes
        if "amount" in node["columns"]
    }
    assert amount_levels == {"confidential"}


# ---------------------------------------------------------------------------
# Fixture: two daily files with a conflicting version across them
# ---------------------------------------------------------------------------


def test_cross_file_conflict_fails_the_build(conflict_build: Build):
    assert not conflict_build.success
    assert conflict_build.statuses[CONFLICT_TEST] == "fail"
    failed = {
        name
        for name, status in conflict_build.statuses.items()
        if status in ("fail", "error")
    }
    assert failed == {CONFLICT_TEST}


def test_cross_file_conflict_reports_only_the_conflicting_order(conflict_build: Build):
    rows = conflict_build.query(
        f"select order_id, n_versions, n_source_files, source_files"
        f' from {AUDIT_SCHEMA}."{CONFLICT_TEST}"'
    )
    assert rows == [("ORD-90001", 2, 2, "orders_2026-11-12.csv, orders_2026-11-13.csv")]


def test_cross_file_exact_duplicate_is_deduplicated_after_trim(conflict_build: Build):
    rows = conflict_build.query(
        "select order_id, count(*) from main.stg_orders group by order_id order by order_id"
    )
    assert rows == [("ORD-90001", 2), ("ORD-90002", 1), ("ORD-90003", 1)]
