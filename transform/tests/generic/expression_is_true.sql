{#-
  Returns the rows where the boolean expression is not true. A null result
  counts as a failure, so a value that could not be cast fails the test.
-#}
{% test expression_is_true(model, expression, column_name=none) %}
select *
from {{ model }}
where not coalesce(({{ expression }}), false)
{% endtest %}
