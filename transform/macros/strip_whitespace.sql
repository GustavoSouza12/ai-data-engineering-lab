{#-
  Remove leading and trailing whitespace exactly like Python's str.strip(),
  which the validator uses for its comparisons (ADR-0009, finding F3).
  DuckDB's trim() without arguments does not remove tabs or line breaks,
  so the character set is explicit.
-#}
{% macro python_whitespace_chars() -%}
  {%- set code_points = [9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760,
                         8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202,
                         8232, 8233, 8239, 8287, 12288] -%}
  ({%- for cp in code_points -%}chr({{ cp }}){%- if not loop.last %} || {% endif -%}{%- endfor -%})
{%- endmacro %}

{% macro strip_whitespace(column) -%}
  trim({{ column }}, {{ python_whitespace_chars() }})
{%- endmacro %}
