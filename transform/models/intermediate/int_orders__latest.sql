{#-
  Current version of each order: the row with the latest updated_at
  (ADR-0009). Ties on updated_at are cross-file conflicts, which
  assert_no_cross_file_conflicting_versions fails on; the tie-break below only
  keeps the build deterministic.
-#}
select *
from {{ ref('stg_orders') }}
qualify row_number() over (
    partition by order_id
    order by updated_at desc nulls last, _loaded_at desc, _source_file desc
) = 1
