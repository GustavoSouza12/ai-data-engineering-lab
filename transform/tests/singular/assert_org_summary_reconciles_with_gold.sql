{#-
  TS-021: org_summary keeps every organization (also those without orders)
  and does not inflate counts or amounts: its totals equal the gold totals.
-#}
with summary as (

    select
        count(*) as n_organizations,
        sum(order_count) as n_orders,
        sum(total_amount_usd) as sum_amount_usd
    from {{ ref('org_summary') }}

),

expected as (

    select
        (select count(*) from {{ ref('organizations') }}) as n_organizations,
        (select count(*) from {{ ref('fct_orders') }}) as n_orders,
        (select coalesce(sum(amount_usd), 0) from {{ ref('fct_orders') }}) as sum_amount_usd

)

select
    summary.n_organizations as summary_n_organizations,
    expected.n_organizations as expected_n_organizations,
    summary.n_orders as summary_n_orders,
    expected.n_orders as expected_n_orders,
    summary.sum_amount_usd as summary_sum_amount_usd,
    expected.sum_amount_usd as expected_sum_amount_usd
from summary
cross join expected
where summary.n_organizations is distinct from expected.n_organizations
   or summary.n_orders is distinct from expected.n_orders
   or summary.sum_amount_usd is distinct from expected.sum_amount_usd
