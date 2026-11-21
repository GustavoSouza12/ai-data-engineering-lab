{#-
  One row per organization, including those without orders (TS-021).
  Orders are aggregated to the organization grain before the join, so the
  join cannot inflate amounts. Every amount is in USD (ADR-0013).
-#}
with organizations as (

    select * from {{ ref('organizations') }}

),

orders_by_organization as (

    select
        organization_id,
        count(*) as order_count,
        count(*) filter (where status = 'completed') as completed_order_count,
        count(*) filter (where status = 'cancelled') as cancelled_order_count,
        sum(amount_usd) as total_amount_usd,
        sum(amount_usd) filter (where status = 'completed') as completed_order_amount_usd
    from {{ ref('fct_orders') }}
    group by organization_id

)

select
    organizations.organization_id,
    organizations.organization_name,
    organizations.organization_type,
    coalesce(orders_by_organization.order_count, 0) as order_count,
    coalesce(orders_by_organization.completed_order_count, 0) as completed_order_count,
    coalesce(orders_by_organization.cancelled_order_count, 0) as cancelled_order_count,
    coalesce(orders_by_organization.total_amount_usd, 0) as total_amount_usd,
    coalesce(orders_by_organization.completed_order_amount_usd, 0) as completed_order_amount_usd
from organizations
left join orders_by_organization
    on orders_by_organization.organization_id = organizations.organization_id
