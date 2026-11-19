# ADR-0014 — Orders JSON and schema changes

- Date: 2026-11-19
- Status: accepted as a design; implementation in F0.4

## Context
A second source delivers orders as JSON, with nested objects (investor, product) and arrays (status history, NAV history). It has to be reconciled with `orders`.

## Decision
1. **RAW keeps the whole document** in a `VARIANT` column (`payload`), plus `_source_file` and `_loaded_at`. Nothing is dropped at load time; parsing happens in staging.
2. **Staging flattens** with `payload:investor.name::string`, `LATERAL FLATTEN` on arrays and `row_number`/`LAG` for the latest status and the previous NAV. On DuckDB, the equivalent uses the native JSON functions.
3. **`investor_name` is PII** (`pii_level = restricted`): it only exists from gold onward, with a tag and a mask; never in marts.
4. **JSON × `orders` reconciliation** by `order_id`: present in both, same amount, same latest status, same organization. Each divergence becomes an issue (ADR-0011).

### Schema change policy

| Situation | Behavior |
|---|---|
| Missing attribute | Becomes `null` in staging (accessing a missing path in a `VARIANT` returns `null`). If the attribute is required by the contract, a `not_null` test with `warn_if`/`error_if` |
| Unexpected type | Converted with `try_cast`/`try_to_number`: a failure becomes `null` and the row goes to `DQ_FAILURES` with the original value; it never brings down the whole pipeline |
| New field | Preserved in the RAW `VARIANT`, breaking nothing. A check compares the keys present with the known ones and opens a `new_json_field` issue for evaluation; it only enters staging through a PR |
| Breaking schema change (rename, restructure) | A contract test fails before publishing (WAP), nothing reaches customers; fixed through a PR, with a new model version if the meaning changed |
