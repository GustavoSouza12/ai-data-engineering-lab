{#-
  Current version of each order: the row with the latest updated_at
  (ADR-0009). An order with a cross-file version conflict (same order_id and
  updated_at, different content in different daily files) is left out as a
  whole and kept in dq_orders_cross_file_conflicts (ADR-0009, amendment
  2026-11-23): no rule says which occurrence is true, and dropping only the
  conflicting version would publish an older version as the current one. No
  winner is ever picked by _loaded_at or file position.

  Without conflicted orders, (order_id, updated_at) is unique here. Only rows
  whose updated_at does not cast can still tie, and they fail the not_null
  test of stg_orders.updated_at; _source_file only keeps such a build
  deterministic.
-#}
with orders as (

    select * from {{ ref('stg_orders') }}

),

conflicted_orders as (

    select distinct order_id
    from {{ ref('dq_orders_cross_file_conflicts') }}

)

select orders.*
from orders
where not exists (
    select 1
    from conflicted_orders
    where conflicted_orders.order_id = orders.order_id
)
qualify row_number() over (
    partition by orders.order_id
    order by orders.updated_at desc nulls last, orders._source_file desc
) = 1
