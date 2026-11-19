# ADR-0009 — `orders` versioning

- Date: 2026-11-19
- Status: accepted (recommendation approved by the user)
- Supersedes: ADR-0003. Changes: ADR-0002 (contract)

## Context
In production, an order changes state and amount over time, and the source sends each change as a new row. ADR-0003 treated any repeated `order_id` as an error and sent everything to quarantine, which would discard legitimate versions. At the same time, the `ORD-00117` case (same ID, different investor and fund, nothing saying which one is right) is still a real conflict.

## Decision

### `orders` contract (replaces the ADR-0002 table)

| Column | Expected type | Required | `pii_level` |
|---|---|---|---|
| `order_id` | text | yes | internal |
| `organization_id` | synthetic text (`ORG-001`) | yes | internal |
| `investor_id` | synthetic text (`INV-0001`) | yes | internal |
| `fund_id` | synthetic text (`FND-001`) | yes | internal |
| `amount` | decimal > 0 | yes | confidential |
| `currency` | `USD`, `EUR`, `BRL` | yes | internal |
| `channel` | `advisor`, `direct`, `platform` | yes | internal |
| `status` | `submitted`, `sponsor_review`, `nigo`, `approved`, `signed`, `completed`, `cancelled` | yes | internal |
| `submitted_at` | ISO 8601 datetime | yes | internal |
| `updated_at` | ISO 8601 datetime of the version | yes | internal |

A version's key is (`order_id`, `updated_at`). RAW keeps every version.

### Three kinds of repetition

| Case | How to recognize it | Where it is handled | Result |
|---|---|---|---|
| Exact duplicate | All columns equal | dbt staging | Keep one row; count it in a metric |
| Version | Same `order_id`, different `updated_at` | dbt intermediate | `row_number() over (partition by order_id order by updated_at desc, _loaded_at desc) = 1` picks the current one; history stays in RAW |
| Conflict | Same (`order_id`, `updated_at`), different content | Python ingestion | Every occurrence goes to quarantine with `conflicting_version` |

Key comparisons use the value with leading and trailing whitespace removed (`strip`). The original value is preserved in the output.

### Approved interpretations (F0.1 review, 2026-11-19)
- **Incomplete row with the same key as a complete one** (finding F1): counts as a conflict, and **both** rows go to quarantine. Conservative posture, chosen by the user: there is no way to prove which row is the true one.
- **`strip` applies to key and content** (finding F3): rows that differ only by leading or trailing whitespace are exact duplicates. Requirement for F0.2: dbt staging applies `trim` before deduplicating, so ingestion and dbt agree.
- **`extra_fields:<n>` reason**: the number of extra fields goes in the reason itself; aggregations use the code before the `:`.

## Rejected alternatives
- Keep ADR-0003: discards legitimate versions and breaks metrics such as "latest version of each order".
- Resolve conflicts with `row_number` by file position: deterministic but arbitrary; it can silently drop a real order.

## Consequences
- The F0.1 validator changes: `duplicate_order_id` goes away and is replaced by `conflicting_version`.
- The generator now produces versions, exact duplicates and conflicts.
- Every order metric starts from the latest version (`int_orders__latest`), never from RAW directly.
