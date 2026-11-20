"""Check the versioned synthetic raw file against the planted counts."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from ingestion import generate_orders as go
from ingestion import validate_orders as vo

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_FILE = REPO_ROOT / "data" / "raw" / "orders" / "orders_2026-11-19.csv"
RUN_TS = "2026-11-19T03:00:00Z"
FILE_DATE_END = go.FILE_DATE_END.isoformat(timespec="seconds")


def _read(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def raw() -> list[dict]:
    return _read(RAW_FILE)


@pytest.fixture(scope="module")
def validated(tmp_path_factory) -> tuple[list[dict], list[dict]]:
    out = tmp_path_factory.mktemp("raw_sample")
    code = vo.run(RAW_FILE, RUN_TS, out / "staging", out / "quarantine")
    assert code == 0
    return _read(out / "staging" / RAW_FILE.name), _read(out / "quarantine" / RAW_FILE.name)


def test_generator_imports_contract_from_validator():
    assert go.COLUMNS is vo.REQUIRED_COLUMNS


def test_raw_file_matches_generator_output(raw):
    # Determinism: the versioned file is what the generator produces with seed 42.
    assert raw == go.generate_orders(go.SEED)


def test_generator_is_deterministic():
    assert go.generate_orders(42) == go.generate_orders(42)


def test_raw_file_shape(raw):
    assert len(raw) == go.N_ROWS
    assert list(raw[0].keys()) == list(vo.REQUIRED_COLUMNS)
    ids = {r["order_id"].strip() for r in raw if r["order_id"].strip()}
    assert len(ids) == go.N_ORDERS
    orgs = {r["organization_id"].strip() for r in raw if r["organization_id"].strip()}
    assert orgs <= {f"ORG-{i:03d}" for i in range(1, go.N_ORGANIZATIONS_WITH_ORDERS + 1)}
    assert not orgs & {f"ORG-{i:03d}" for i in range(16, 21)}  # seeds without orders in F0.2


def test_raw_file_planted_structural_errors(raw):
    blank = [r for r in raw if any(r[c] == "" for c in vo.REQUIRED_COLUMNS)]
    spaces = [r for r in raw if any(r[c] == go.WHITESPACE_VALUE for c in vo.REQUIRED_COLUMNS)]
    extras = [r for r in raw if None in r]
    assert len(blank) == go.N_EMPTY_FIELD
    assert len(spaces) == go.N_WHITESPACE_FIELD
    assert len(extras) == go.N_EXTRA_FIELD
    assert all(r[None] == [go.EXTRA_FIELD_VALUE] for r in extras)


def test_raw_file_versions_progress_in_time(raw):
    planted_ids = {
        r["order_id"]
        for r in raw
        if None in r
        or any(r[c].strip() == "" for c in vo.REQUIRED_COLUMNS)
        or r["updated_at"] > FILE_DATE_END
    }
    by_order: dict[str, list[dict]] = defaultdict(list)
    for r in raw:
        if r["order_id"] not in planted_ids:
            by_order[r["order_id"]].append(r)

    for rows in by_order.values():
        for r in rows:
            assert r["submitted_at"] <= r["updated_at"] <= FILE_DATE_END
        distinct = sorted({r["updated_at"] for r in rows})
        if len(distinct) > 1:
            ordered = sorted(rows, key=lambda r: r["updated_at"])
            statuses = tuple(r["status"] for r in ordered)
            assert statuses in go.PROGRESSIONS_2 + go.PROGRESSIONS_3
            assert len(distinct) == len(rows)  # strictly increasing updated_at
            assert len({r["submitted_at"] for r in rows}) == 1

    n_versions = Counter(len({r["updated_at"] for r in rows}) for rows in by_order.values())
    assert n_versions[2] == go.N_ORDERS_2_VERSIONS
    assert n_versions[3] == go.N_ORDERS_3_VERSIONS


def test_raw_file_validated_counts(validated):
    staging, quarantine = validated
    assert len(staging) == go.EXPECTED_STAGING_ROWS
    assert len(quarantine) == go.EXPECTED_QUARANTINE_ROWS
    assert len(staging) + len(quarantine) == go.N_ROWS

    counts = vo.reason_counts(quarantine)
    n_missing = sum(n for reason, n in counts.items() if reason.startswith("missing_"))
    assert n_missing == go.N_EMPTY_FIELD + go.N_WHITESPACE_FIELD
    assert counts["conflicting_version"] == 2 * go.N_CONFLICTS
    assert counts["extra_fields"] == go.N_EXTRA_FIELD
    assert "duplicate_order_id" not in counts
    # Each planted row has a single reason.
    assert all(vo.REASON_SEPARATOR not in r["reject_reason"] for r in quarantine)

    conflict_keys = Counter(
        (r["order_id"], r["updated_at"])
        for r in quarantine
        if r["reject_reason"] == "conflicting_version"
    )
    assert len(conflict_keys) == go.N_CONFLICTS
    assert set(conflict_keys.values()) == {2}


def test_raw_file_repetitions_pass_to_staging(validated):
    staging, _ = validated
    assert vo.count_exact_duplicates(staging) == go.N_EXACT_DUPLICATES
    assert vo.count_versioned_orders(staging) == go.N_VERSIONED_ORDERS


def test_raw_file_semantic_errors_stay_in_staging(validated):
    staging, quarantine = validated
    negatives = [r for r in staging if r["amount"].startswith("-")]
    fax = [r for r in staging if r["channel"] == go.INVALID_CHANNEL]
    future = [r for r in staging if r["updated_at"] > FILE_DATE_END]
    assert len(negatives) == go.N_NEGATIVE_AMOUNT
    assert len(fax) == go.N_INVALID_CHANNEL
    assert len(future) == go.N_FUTURE_UPDATED_AT
    assert future[0]["updated_at"] == go.FUTURE_UPDATED_AT
    assert not any(
        r["amount"].startswith("-")
        or r["channel"] == go.INVALID_CHANNEL
        or r["updated_at"] > FILE_DATE_END
        for r in quarantine
    )
