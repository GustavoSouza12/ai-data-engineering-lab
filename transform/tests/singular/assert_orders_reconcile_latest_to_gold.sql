{#-
  TS-011: count and sum of amount per currency match between the latest
  version of each order (int_orders__latest) and gold (fct_orders). Amounts
  are only summed within one currency (ADR-0013).
-#}
with latest as (

    select currency, count(*) as n_orders, sum(amount) as sum_amount
    from {{ ref('int_orders__latest') }}
    group by currency

),

gold as (

    select currency, count(*) as n_orders, sum(amount) as sum_amount
    from {{ ref('fct_orders') }}
    group by currency

)

select
    coalesce(latest.currency, gold.currency) as currency,
    latest.n_orders as latest_n_orders,
    gold.n_orders as gold_n_orders,
    latest.sum_amount as latest_sum_amount,
    gold.sum_amount as gold_sum_amount
from latest
full outer join gold
    on gold.currency is not distinct from latest.currency
where latest.n_orders is distinct from gold.n_orders
   or latest.sum_amount is distinct from gold.sum_amount
