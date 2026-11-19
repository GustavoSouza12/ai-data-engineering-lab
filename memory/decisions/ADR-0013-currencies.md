# ADR-0013 — Amounts in several currencies

- Date: 2026-11-19
- Status: accepted (coordinator's finding while analyzing the technical case)

## Context
`orders.amount` comes in `USD`, `EUR` or `BRL`. Summing `amount` directly mixes currencies and produces a meaningless total that no count test catches.

## Decision
- Gold keeps the original `amount` and `currency` **and** `amount_usd`, converted at the rate for the `submitted_at` date.
- Rates come from a synthetic `fx_rates` seed (`rate_date`, `currency`, `rate_to_usd`) in phase 0; with a real source, from an FX provider loaded into RAW.
- Every monetary aggregation uses `amount_usd` or groups by `currency`. Summing `amount` across currencies is forbidden and becomes a reviewer rule.
- Test: every order has a rate for its date and currency (`relationships` with `fx_rates`); a missing rate is an `error`.

## Consequences
Metrics such as `completed_order_amount` become `completed_order_amount_usd`. Sum reconciliation is done in USD and per original currency.
