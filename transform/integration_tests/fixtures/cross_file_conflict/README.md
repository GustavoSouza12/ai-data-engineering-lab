# Fixture: conflict across daily files

Two raw daily files that each pass the validator on their own (it sees one file at a time):

| order_id | `orders_2026-11-12.csv` | `orders_2026-11-13.csv` | Expected in dbt |
|---|---|---|---|
| `ORD-90001` | version at `2026-11-10T09:00:00` | same `updated_at`, different `investor_id` and `amount` | conflict: both rows in `dq_orders_cross_file_conflicts`, order not in gold, `assert_no_cross_file_conflicting_versions` warns |
| `ORD-90002` | version at `2026-11-10T10:00:00` | same version, `fund_id` with a trailing space | exact duplicate after `trim`: one row, no conflict |
| `ORD-90003` | — | new order | one row |

Used by `transform/integration_tests/test_dbt_project.py`.
