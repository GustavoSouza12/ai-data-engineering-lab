{#-
  TS-026: orders with a cross-file version conflict, one row per order. The
  conflicting occurrences are already in dq_orders_cross_file_conflicts and
  the order is out of gold (ADR-0009, amendment 2026-11-23), so this test does
  not block the publish of the other orders: it warns from the first conflicted
  order and errors only above var('cross_file_conflict_error_threshold')
  conflicted orders, the T3 pattern (ADR-0017). The failures are stored.
  The severity var stays error: dbt applies error_if only at severity error.
-#}
{{ config(
    severity=var('cross_file_conflict_severity'),
    warn_if='>0',
    error_if='>' ~ var('cross_file_conflict_error_threshold'),
) }}

select
    order_id,
    count(distinct updated_at) as n_conflicting_versions,
    count(*) as n_occurrences,
    count(distinct _source_file) as n_source_files,
    string_agg(distinct _source_file, ', ' order by _source_file) as source_files
from {{ ref('dq_orders_cross_file_conflicts') }}
group by order_id
