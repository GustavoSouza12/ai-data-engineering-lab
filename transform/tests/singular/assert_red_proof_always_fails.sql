-- Red proof for MVP-03: this test always fails. Never merge.
select order_id from {{ ref('fct_orders') }}
