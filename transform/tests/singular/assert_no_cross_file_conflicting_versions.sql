{#-
  TS-026: orders with a cross-file version conflict brought by the newest
  batch, one row per order. A conflict belongs to the newest batch when one of
  its occurrences comes from the daily file with the latest file date in
  stg_orders, so the threshold is per batch, not cumulative: a long chain of
  daily files with one conflict each never errors on conflicts that earlier
  batches already brought. Every conflict, old or new, stays in
  dq_orders_cross_file_conflicts and out of gold (ADR-0009, amendment
  2026-11-23), so this test does not block the publish of the other orders:
  it warns from the first conflicted order of the batch and errors only above
  var('cross_file_conflict_error_threshold') of them, the T3 pattern
  (ADR-0017). The failures are stored. The severity var stays error: dbt
  applies error_if only at severity error.
-#}
{{ config(
    severity=var('cross_file_conflict_severity'),
    warn_if='>0',
    error_if='>' ~ var('cross_file_conflict_error_threshold'),
) }}

with newest_batch as (

    select max(_source_file_date) as file_date
    from {{ ref('stg_orders') }}

),

conflicts as (

    select
        order_id,
        count(distinct updated_at) as n_conflicting_versions,
        count(*) as n_occurrences,
        count(distinct _source_file) as n_source_files,
        string_agg(distinct _source_file, ', ' order by _source_file) as source_files,
        max(_source_file_date) as newest_file_date
    from {{ ref('dq_orders_cross_file_conflicts') }}
    group by order_id

)

select
    conflicts.order_id,
    conflicts.n_conflicting_versions,
    conflicts.n_occurrences,
    conflicts.n_source_files,
    conflicts.source_files
from conflicts
inner join newest_batch
    on conflicts.newest_file_date = newest_batch.file_date
