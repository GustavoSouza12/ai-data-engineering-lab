"""End-to-end local pipeline on the sample plus daily files (TS-020 horizon, ADR-0013).

Runs the real steps in a temporary directory: generator (base sample and the next
two daily files) -> validator with ``--summary-json`` -> batch guard -> ``dbt build``
on a temporary DuckDB file (`dev` target). Daily files submit new orders on their
file date, so the build only passes when ``fx_rates`` covers those dates. Nothing
is written to the worktree.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_DIR = REPO_ROOT / "transform"
FIRST_DATE = date(2026, 11, 19)
N_DAILY_FILES = 2
SEMANTIC_TESTS = {  # T3 (ADR-0017): the planted errors of the sample, warn only
    "ts009_fct_orders_channel_accepted",
    "ts010_fct_orders_amount_castable_and_positive",
    "ts012_fct_orders_timestamps_within_file_date",
}
# Each daily file of the current generator plants one cross-file conflict, which
# errors by default (ADR-0009). This run lowers that test to a warning so that the
# FX coverage of the daily files is what decides the result.
CONFLICT_TEST = "assert_no_cross_file_conflicting_versions"


def _run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", *args], capture_output=True, text=True, **kwargs
    )


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> dict:
    tmp = tmp_path_factory.mktemp("local_pipeline")
    raw_dir, staging, quarantine = tmp / "raw", tmp / "staging", tmp / "quarantine"
    generated = _run(
        [
            "ingestion.generate_orders",
            "--date",
            FIRST_DATE.isoformat(),
            "--days",
            str(1 + N_DAILY_FILES),
            "--output-dir",
            str(raw_dir),
        ],
        cwd=REPO_ROOT,
    )
    assert generated.returncode == 0, generated.stderr
    raw_files = sorted(raw_dir.glob("orders_*.csv"))
    assert [f.name for f in raw_files] == [
        f"orders_{(FIRST_DATE + timedelta(days=i)).isoformat()}.csv"
        for i in range(1 + N_DAILY_FILES)
    ]

    for raw in raw_files:
        file_date = date.fromisoformat(raw.stem.removeprefix("orders_"))
        summary = tmp / "summaries" / f"{raw.stem}.json"
        validated = _run(
            [
                "ingestion.validate_orders",
                "--input",
                str(raw),
                "--run-ts",
                f"{file_date.isoformat()}T03:00:00Z",
                "--staging-dir",
                str(staging),
                "--quarantine-dir",
                str(quarantine),
                "--summary-json",
                str(summary),
            ],
            cwd=REPO_ROOT,
        )
        assert validated.returncode == 0, validated.stderr
        guarded = _run(
            ["ingestion.batch_guard", "--summary-json", str(summary)], cwd=REPO_ROOT
        )
        assert guarded.returncode == 0, guarded.stdout + guarded.stderr

    database, target_dir = tmp / "lab_test.duckdb", tmp / "target"
    built = _run(
        [
            "dbt.cli.main",
            "build",
            "--project-dir",
            str(PROJECT_DIR),
            "--profiles-dir",
            str(PROJECT_DIR),
            "--target",
            "dev",
            "--target-path",
            str(target_dir),
            "--log-path",
            str(tmp / "logs"),
            "--vars",
            json.dumps(
                {
                    "orders_staging_dir": str(staging),
                    "cross_file_conflict_severity": "warn",
                }
            ),
        ],
        cwd=PROJECT_DIR,
        env={**os.environ, "LAB_DUCKDB_PATH": str(database)},
    )
    run_results = json.loads((target_dir / "run_results.json").read_text())
    statuses = {
        r["unique_id"].split(".")[2]: r["status"] for r in run_results["results"]
    }
    return {"build": built, "statuses": statuses, "database": database}


def test_dbt_build_exits_0_with_only_the_expected_warnings(pipeline: dict):
    build = pipeline["build"]
    assert build.returncode == 0, build.stdout + build.stderr
    statuses = pipeline["statuses"]
    counts = Counter(statuses.values())
    assert counts["error"] == counts["fail"] == counts["skipped"] == 0
    warned = {name for name, status in statuses.items() if status == "warn"}
    assert warned == SEMANTIC_TESTS | {CONFLICT_TEST}


def test_every_order_of_the_daily_files_has_a_rate(pipeline: dict):
    assert pipeline["statuses"]["assert_every_order_has_fx_rate"] == "pass"
    with duckdb.connect(str(pipeline["database"]), read_only=True) as con:
        rows = con.execute(
            "select cast(o.submitted_at as date)::varchar as d, count(*),"
            " count(r.rate_to_usd), count(o.amount_usd)"
            " from main.fct_orders o left join main.fx_rates r"
            " on r.currency = o.currency and r.rate_date = cast(o.submitted_at as date)"
            " where cast(o.submitted_at as date) >= ? group by d order by d",
            [FIRST_DATE + timedelta(days=1)],
        ).fetchall()
    daily_dates = [(FIRST_DATE + timedelta(days=i)).isoformat() for i in (1, 2)]
    assert [d for d, *_ in rows] == daily_dates
    for _, n, n_rated, n_usd in rows:
        assert n == n_rated == n_usd > 0
