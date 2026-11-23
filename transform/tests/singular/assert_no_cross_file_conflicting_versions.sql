{#-
  Conflict across daily files: the same version key (order_id, updated_at)
  with different content. Ingestion quarantines conflicts inside one file
  (ADR-0009), but it sees one file at a time. stg_orders has already removed
  exact duplicates, including copies of a version in several files, so any
  key that is still repeated has different content.
  The severity comes from var('cross_file_conflict_severity') (default error);
  the final gold policy for these conflicts is pending the owner's decision.
-#}
{{ config(severity=var('cross_file_conflict_severity')) }}

select
    order_id,
    updated_at,
    count(*) as n_versions,
    count(distinct _source_file) as n_source_files,
    string_agg(distinct _source_file, ', ' order by _source_file) as source_files
from {{ ref('stg_orders') }}
where order_id is not null
  and updated_at is not null
group by order_id, updated_at
having count(*) > 1
