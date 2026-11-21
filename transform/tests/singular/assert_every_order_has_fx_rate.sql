{#-
  TS-020 (ADR-0013): every order has an exchange rate for its submitted_at
  date and currency. A missing rate is an error.
-#}
select
    orders.order_id,
    orders.currency,
    cast(orders.submitted_at as date) as submitted_date
from {{ ref('fct_orders') }} as orders
left join {{ ref('fx_rates') }} as fx_rates
    on fx_rates.currency = orders.currency
    and fx_rates.rate_date = cast(orders.submitted_at as date)
where fx_rates.rate_to_usd is null
