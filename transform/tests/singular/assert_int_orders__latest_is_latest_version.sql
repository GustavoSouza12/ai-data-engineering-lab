{#-
  TS-019: every order in staging appears in int_orders__latest exactly with
  its latest updated_at. Returns orders that are missing or not the latest.
-#}
with latest_in_staging as (

    select order_id, max(updated_at) as max_updated_at
    from {{ ref('stg_orders') }}
    group by order_id

)

select
    latest_in_staging.order_id,
    latest_in_staging.max_updated_at,
    int_orders.updated_at as picked_updated_at
from latest_in_staging
left join {{ ref('int_orders__latest') }} as int_orders
    on int_orders.order_id = latest_in_staging.order_id
where int_orders.order_id is null
   or int_orders.updated_at is distinct from latest_in_staging.max_updated_at
