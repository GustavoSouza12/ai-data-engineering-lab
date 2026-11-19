# ADR-0003 — Duplicate `order_id` rule

- Date: 2026-11-19
- Status: **superseded by ADR-0009** on 2026-11-19 (the reasoning about conflicts still holds for the "same `order_id` and same `updated_at`" case)

## Context
An `order_id` can appear more than once in the same raw file.

## Decision
All occurrences of a duplicate `order_id` go to quarantine with `reject_reason = duplicate_order_id`. None goes to staging.

## Rejected alternatives
- Keep the first occurrence: depends on row order, which is not guaranteed; the result would change if the file were reordered, breaking idempotency.
- Keep the latest by `submitted_at`: requires trusting a field that has not been validated yet.

## Consequences
More rejections, but deterministic and auditable. Resolving duplicates is left to an explicit process, outside phase 0.
