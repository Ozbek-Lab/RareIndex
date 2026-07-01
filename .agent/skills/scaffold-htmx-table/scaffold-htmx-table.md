---
name: scaffold-htmx-table
description: Generates a Django CBV, Table, and FilterSet for a model (e.g., Variant, Sample) with HTMX partial rendering support.
---

# Scaffold HTMX Table

Use this skill when the user asks to "create a table for [Model]" or "add a list view for [Model]".

## Strategy
You will generate three files (or append to them): `tables.py`, `filters.py`, and `views.py`. You must use `django-template-partials` to handle the HTMX swaps efficiently.

## 1. tables.py
Create a `django_tables2.Table` class.
- Use `TemplateColumn` for fields requiring HTML (e.g., status badges).
- Enable `attrs={"class": "table table-hover", "hx-target": "closest .table-container"}` to ensure sorting clicks trigger HTMX swaps.

## 2. filters.py
Create a `django_filters.FilterSet` class.
- Use `django_filters.CharFilter(lookup_expr='icontains')` for text search.
- **Critical:** For genomic fields (e.g., `Gene`), use `MultipleChoiceFilter` to allow selecting multiple genes at once.

## 3. views.py (The Pattern)
Implement a Class-Based View (CBV) inheriting `SingleTableMixin` and `FilterView`.

```python
# views.py template pattern
from django_tables2 import SingleTableMixin
from django_filters.views import FilterView
from django.shortcuts import render

class {Model}ListView(SingleTableMixin, FilterView):
    model = {Model}
    table_class = {Model}Table
    filterset_class = {Model}Filter
    template_name = "{app_name}/{model}_list.html"
    paginate_by = 25

    def get_template_names(self):
        # Django 6 / django-template-partials pattern
        if self.request.htmx:
            return [f"{self.template_name}#table_container"]
        return [self.template_name]

4. Template Structure
The template MUST use the partialdef tag to wrap the table and pagination.

{% extends "base.html" %}
{% load render_table from django_tables2 %}
{% load partials %}

{% block content %}
<div class="table-container">
    <!-- Filter Form -->
    <form hx-get="." hx-target=".table-container" hx-trigger="change, keyup delay:500ms from:input">
        {{ filter.form.as_p }}
    </form>

    <!-- Table Partial -->
    {% partialdef table_container %}
        {% render_table table %}
    {% endpartialdef %}
</div>
{% endblock %}
