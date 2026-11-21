#!/usr/bin/env bash
# Local end-to-end run (MVP-06): generator -> validator -> batch guard -> RAW load
# -> dbt build, all on one local DuckDB file.
#
# Usage: scripts/run_local_pipeline.sh
# Exits non-zero as soon as a step fails. Only the local DuckDB `dev` target is
# used; no cloud resources are touched. The validator's --debug flag is never
# passed (it may print paths and values).
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$repo_root"

raw_file="data/raw/orders/orders_2026-11-19.csv"
source_file="$(basename -- "$raw_file")"
run_ts="2026-11-19T03:00:00Z"
summary_json="data/reports/${source_file%.csv}.json"
# The dbt dev target's default file (transform/profiles.yml), seen from the repo root.
duckdb_file="transform/lab_dev.duckdb"

echo "==> uv sync"
uv sync --locked

echo "==> generate ${raw_file}"
uv run python -m ingestion.generate_orders --output "$raw_file"

echo "==> validate"
# A summary left by an earlier run must never reach the batch guard: the validator
# writes a new one only on success.
rm -f -- "$summary_json"
uv run python -m ingestion.validate_orders --input "$raw_file" --run-ts "$run_ts" \
    --summary-json "$summary_json"

echo "==> batch guard"
uv run python -m ingestion.batch_guard --summary-json "$summary_json"

echo "==> load RAW (raw.orders, raw.orders_quarantine)"
uv run python -m ingestion.load_raw --source-file "$source_file" --database "$duckdb_file" \
    --summary-json "$summary_json"

echo "==> dbt build (target dev, DuckDB)"
cd transform
# Pin the file: an inherited LAB_DUCKDB_PATH would make dbt read another database.
LAB_DUCKDB_PATH="lab_dev.duckdb" uv run dbt build --profiles-dir . --target dev

echo "==> local pipeline finished"
