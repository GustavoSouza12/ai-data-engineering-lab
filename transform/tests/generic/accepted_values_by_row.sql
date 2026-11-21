{#-
  Like the built-in accepted_values, but returns the offending rows instead of
  one row per distinct value, so store_failures keeps the keys of the rows
  that failed (T3, ADR-0017). Null values are left to not_null.
-#}
{% test accepted_values_by_row(model, column_name, values) %}
select *
from {{ model }}
where {{ column_name }} is not null
  and {{ column_name }} not in (
    {%- for value in values %}'{{ value }}'{% if not loop.last %}, {% endif %}{% endfor -%}
  )
{% endtest %}
