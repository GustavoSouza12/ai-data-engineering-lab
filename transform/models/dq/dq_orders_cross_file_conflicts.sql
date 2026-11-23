{#-
  Quarantine of cross-file version conflicts (ADR-0009, amendment 2026-11-23):
  every occurrence of a version key (order_id, updated_at) that has different
  content in different daily files. Ingestion quarantines conflicts inside one
  file, but it sees one file at a time. stg_orders has already removed exact
  duplicates, including copies of a version in several files, so any key that
  is still repeated has different content. No occurrence is picked as the
  winner: int_orders__latest leaves the whole order out of gold.

  Invariant: every key here spans more than one _source_file, because the
  validator quarantines a conflict inside one file. The model does not filter
  on count(distinct _source_file) > 1 on purpose: an in-file conflict that
  bypassed validation would then reach int_orders__latest and be resolved
  silently; here it is quarantined like the others.
-#}
with orders as (

    select * from {{ ref('stg_orders') }}

),

conflicting_keys as (

    select
        order_id,
        updated_at
    from orders
    where order_id is not null
      and updated_at is not null
    group by order_id, updated_at
    having count(*) > 1

)

select
    orders.order_id,
    orders.organization_id,
    orders.investor_id,
    orders.fund_id,
    orders.amount,
    orders.currency,
    orders.channel,
    orders.status,
    orders.submitted_at,
    orders.updated_at,
    orders._source_file,
    orders._source_file_date,
    orders._loaded_at,
    'conflicting_version_cross_file' as reject_reason
from orders
inner join conflicting_keys
    on conflicting_keys.order_id = orders.order_id
    and conflicting_keys.updated_at = orders.updated_at
