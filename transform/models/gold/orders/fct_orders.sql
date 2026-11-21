{#-
  Gold orders: one row per order, current version, with amount_usd converted
  at the rate of the submitted_at date (ADR-0013). Left join, so an order
  without a rate stays visible and fails assert_every_order_has_fx_rate.
-#}
with orders as (

    select * from {{ ref('int_orders__latest') }}

),

fx_rates as (

    select * from {{ ref('fx_rates') }}

)

select
    orders.order_id,
    orders.organization_id,
    orders.investor_id,
    orders.fund_id,
    orders.amount,
    orders.currency,
    fx_rates.rate_to_usd,
    cast(round(orders.amount * fx_rates.rate_to_usd, 2) as decimal(18, 2)) as amount_usd,
    orders.channel,
    orders.status,
    orders.submitted_at,
    orders.updated_at,
    orders._source_file,
    orders._source_file_date,
    orders._loaded_at
from orders
left join fx_rates
    on fx_rates.currency = orders.currency
    and fx_rates.rate_date = cast(orders.submitted_at as date)
