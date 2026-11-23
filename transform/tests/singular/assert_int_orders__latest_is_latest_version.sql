{#-
  TS-019: every order in staging without a cross-file conflict appears in
  int_orders__latest exactly with its latest updated_at, and no order with a
  cross-file conflict appears there (ADR-0009, amendment 2026-11-23). Returns
  orders that are missing, not the latest, or conflicted but present.
-#}
with conflicted_orders as (

    select distinct order_id
    from {{ ref('dq_orders_cross_file_conflicts') }}

),

latest_in_staging as (

    select
        order_id,
        max(updated_at) as max_updated_at
    from {{ ref('stg_orders') }}
    group by order_id

),

expected as (

    select
        latest_in_staging.order_id,
        latest_in_staging.max_updated_at,
        conflicted_orders.order_id is not null as is_conflicted
    from latest_in_staging
    left join conflicted_orders
        on conflicted_orders.order_id = latest_in_staging.order_id

)

select
    expected.order_id,
    expected.max_updated_at,
    expected.is_conflicted,
    int_orders.updated_at as picked_updated_at
from expected
left join {{ ref('int_orders__latest') }} as int_orders
    on int_orders.order_id = expected.order_id
where (expected.is_conflicted and int_orders.order_id is not null)
   or (
       not expected.is_conflicted
       and (
           int_orders.order_id is null
           or int_orders.updated_at is distinct from expected.max_updated_at
       )
   )
