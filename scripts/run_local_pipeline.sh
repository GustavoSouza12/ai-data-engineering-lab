#!/usr/bin/env bash
# Local end-to-end run (F0.2a): generator -> validator -> dbt build on DuckDB.
#
# Usage: scripts/run_local_pipeline.sh
# Exits non-zero as soon as a step fails. Only the local DuckDB `dev` target is
# used; no cloud resources are touched. The validator's --debug flag is never
# passed (it may print paths and values).
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$repo_root"

raw_file="data/raw/orders/orders_2026-11-19.csv"
run_ts="2026-11-19T03:00:00Z"

echo "==> uv sync"
uv sync --locked

echo "==> generate ${raw_file}"
uv run python -m ingestion.generate_orders --output "$raw_file"

echo "==> validate"
uv run python -m ingestion.validate_orders --input "$raw_file" --run-ts "$run_ts"

echo "==> dbt build (target dev, DuckDB)"
cd transform
uv run dbt build --profiles-dir . --target dev

echo "==> local pipeline finished"
