# ADR-0005 — Folder structure and data in git

- Date: 2026-11-19
- Status: accepted (decision delegated by the user to the coordinator)

## Decision
```
ingestion/                  Python generation and validation code
  tests/                    pytest
transform/                  dbt project (models/, tests/, macros/ live inside it)
data/raw/orders/            small synthetic sample, versioned
data/staging/orders/        valid output, not in git
data/quarantine/orders/     rejected rows, not in git
```
- `transform/` avoids clashing with `models/` and `tests/` from section 6 of the architecture.
- Version only the synthetic raw sample, so tests are reproducible. Outputs, `.venv`, `*.duckdb` and `transform/target/` are in `.gitignore`.

## Rejected alternatives
- Version no data at all: tests would depend on generating data first, one more point of failure.
- Version the outputs: git would become data storage.
