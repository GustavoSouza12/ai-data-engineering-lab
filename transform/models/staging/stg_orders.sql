{#-
  One row per distinct order version across every validated daily file.

  1. Trim every value the same way the validator compares them (ADR-0009, F3).
  2. Only then drop exact duplicates: rows whose contract columns are equal
     after trimming. Copies of the same version in different daily files are
     exact duplicates too; the first load is kept.
  3. Cast. A value that does not cast becomes null and fails a gold test.
-#}
{%- set contract_columns = [
    'order_id', 'organization_id', 'investor_id', 'fund_id', 'amount',
    'currency', 'channel', 'status', 'submitted_at', 'updated_at'
] -%}

with source as (

    select * from {{ source('orders_staging', 'orders') }}

),

trimmed as (

    select
        {%- for column in contract_columns %}
        {{ strip_whitespace(column) }} as {{ column }},
        {%- endfor %}
        {{ strip_whitespace('_source_file') }} as _source_file,
        {{ strip_whitespace('_loaded_at') }} as _loaded_at
    from source

),

deduplicated as (

    select *
    from trimmed
    qualify row_number() over (
        partition by {{ contract_columns | join(', ') }}
        order by _loaded_at, _source_file
    ) = 1

)

select
    order_id,
    organization_id,
    investor_id,
    fund_id,
    try_cast(amount as decimal(18, 2)) as amount,
    currency,
    channel,
    status,
    try_cast(submitted_at as timestamp) as submitted_at,
    try_cast(updated_at as timestamp) as updated_at,
    _source_file,
    try_cast(regexp_extract(_source_file, '(\d{4}-\d{2}-\d{2})', 1) as date) as _source_file_date,
    try_cast(_loaded_at as timestamptz) as _loaded_at
from deduplicated
