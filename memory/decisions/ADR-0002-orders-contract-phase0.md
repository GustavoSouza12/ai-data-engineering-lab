# ADR-0002 — Phase 0 dataset and contract: `orders`

- Date: 2026-11-19
- Status: accepted (decision delegated by the user to the coordinator); **column table superseded by ADR-0009** (adds `organization_id`, `status`, `updated_at`). The structural × semantic split still applies; **"no PII" amended by ADR-0018** (`investors` uses obvious placeholder values treated as PII)

## Context
The roadmap talks about "transactions". The architecture's domain is fund subscriptions, and the `orders` source will be loaded into `RAW` in phase 1. Generic banking columns would make phase 0 throwaway work.

## Decision
Phase 0 uses the synthetic `orders` source, with no PII.

| Column | Expected type | Required | `pii_level` |
|---|---|---|---|
| `order_id` | text, PK | yes | internal |
| `investor_id` | synthetic text (`INV-0001`) | yes | internal |
| `fund_id` | synthetic text (`FND-001`) | yes | internal |
| `amount` | decimal > 0 | yes | confidential |
| `currency` | ISO 4217 (`USD`, `EUR`, `BRL`) | yes | internal |
| `channel` | `advisor`, `direct`, `platform` | yes | internal |
| `submitted_at` | ISO 8601 datetime | yes | internal |

Ingestion adds `_source_file` and `_loaded_at`.

Split of responsibility:
- **Python ingestion (structural):** complete header, required field empty or whitespace-only, duplicate `order_id`. Rejected rows go to quarantine with a `reject_reason`.
- **dbt (semantic):** types (`try_cast`), `amount > 0`, accepted values of `channel` and `currency`, `unique` and `not_null` on the PK, reconciliation.

## Rejected alternatives
- Generic banking transactions: not reusable in phase 1.
- Validate types in Python: would duplicate rules that belong to dbt in the target architecture.

## Consequences
English names, aligned with dbt and Snowflake. No personal data in phase 0.
