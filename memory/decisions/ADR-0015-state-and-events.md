# ADR-0015 — State (`orders`) and events (`order_events`)

- Date: 2026-11-19
- Status: accepted (discussion with the user about the usefulness of `order_events`)

## Context
`orders` is versioned (ADR-0009) and already has `status`, which makes `order_events` look redundant. In production it is not: cursor-based incremental ingestion captures the state at sync time and loses transitions that happen between two reads; `updated_at` marks any change to the row, not the status transition; and only the event carries who acted and why.

## Decision
- **`orders` answers "what the order looks like"**: amount, organization, fund, current `status` (from the latest version).
- **`order_events` answers "what happened, when and why"**: `event_id`, `order_id`, `status`, `event_at`, `actor_type` (`investor`, `advisor`, `sponsor`, `system`), `nigo_reason` (only on `nigo`).
- Transition dates (for example `latest_completed_order_at`, cycle time, time in sponsor review) **always** come from `order_events`.
- Consistency test: the `status` of the latest `orders` version must equal the order's latest event; a divergence becomes an issue (ADR-0011), with `warn_if`.
- In the synthetic data (F0.2), `order_events` has transitions that do **not** appear in the `orders` versions, to reproduce the loss between syncs.

## Consequences
`org_summary` uses `orders` for counts and amounts and `order_events` for completion dates, each aggregated to the order grain before the join.
