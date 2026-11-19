# RB-001 — A metric jumped and every pipeline is green

**Example:** completed investments were US$ 10M yesterday, today they are US$ 27M, and only ~US$ 1M of new volume was expected.

**Principle:** measure **the same metric, with the same filter, at every boundary**, today and yesterday. The first layer where the number diverges is where the error came in (binary search across layers). "Green pipeline" only means the code ran, not that the data is right.

## 0. Containment (first 15 minutes)
- If the metric reaches customers (ADR-0012): consider a `SWAP` back to the previous gold and notify CS.
- Open an incident issue with an owner and a timestamp.

## 1. Every boundary, the same question

| Layer | Question | Query (skeleton) |
|---|---|---|
| Consumer | Does the dashboard apply a different filter or cache? | Compare the card's SQL with the mart |
| Mart | Does the mart diverge from gold? | `sum(amount_usd)` in mart × gold, same filter |
| Gold | Does gold have more rows than orders? | `count(*)` × `count(distinct order_id)` in `fct_orders` |
| Intermediate | Is the latest version being picked? | `count(*)` × `count(distinct order_id)` in `int_orders__latest` |
| Staging | Did extra versions or duplicates arrive today? | Count by `_source_file` and by `_loaded_at::date` |
| RAW | Was today's load duplicated? | Rows by `_source_file`; was the same file loaded twice? |
| Source | Does the source really have that value? | Same sum directly on the source, same filter |

## 2. The most common causes and their signatures

| Cause | Signature |
|---|---|
| Join fan-out (e.g. `orders` × `order_events` before aggregating) | `count(*)` > `count(distinct order_id)` only from the join layer onward |
| Versions summed (no `row_number` on the latest version) | Sum ≈ sum of all versions; grows with every source update |
| Duplicate load (rerun without idempotency) | Same `_source_file` loaded twice in RAW; an exact multiple of the expected value |
| Currencies summed (ADR-0013) | Jump proportional to the day's share of BRL or EUR |
| Definition change | A recent PR changed the "completed" filter (check `git log` on the models) |
| Real error at the source | The source already shows the US$ 27M |

## 3. Decision
- **Source error:** page the owner in `DQ_OWNERS`, open an issue (ADR-0011), annotate the metric on the dashboard.
- **Pipeline error:** fix through a PR with a test that reproduces the problem, reprocess the affected dates (idempotent backfill, section 3.4) and publish through WAP.

## 4. After the incident
- Which test should have caught this? Write it (for example, `unique` on the `fct_orders` grain, or a daily sum check against the 7-day average).
- Record the cause and the fix in `memory/` and in this runbook.
