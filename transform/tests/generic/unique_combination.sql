{#- Returns one row per combination of the columns that appears more than once. -#}
{% test unique_combination(model, combination) %}
select
    {{ combination | join(', ') }},
    count(*) as n_records
from {{ model }}
group by {{ combination | join(', ') }}
having count(*) > 1
{% endtest %}
