---
name: implement-infinite-scroll
description: Converts a standard django-tables2 table or a dropdown into an infinite scrolling UI with dynamic result counters.
---

# Implement Infinite Scroll

Use this skill when the user requests "infinite scroll", "load more on scroll", or "lazy loading" for tables or dropdowns.

## 1. Table Implementation Strategy
We do **not** use JavaScript libraries for this. We use HTMX's `revealed` trigger on the last row of the current page.

### The View Pattern (views.py)
Ensure the view inherits from `HqHtmxActionMixin` or handles HTMX context.
- **Pagination:** Must be enabled (e.g., `paginate_by = 20`).
- **Counts:** Calculate `total_filtered` (queryset count) and `currently_shown` (page_size * current_page_number).

### The Template Pattern (Table Body)
Override the `table_body` block in `django-tables2`. The logic must detect the **last row** of the current page loop.

```html
{% load django_tables2 %}
<tbody>
    {% for row in table.paginated_rows %}
        {# Check if this is the absolute last item of the current page #}
        {% if forloop.last and table.page.has_next %}
            <tr 
                hx-get="{% querystring table.prefixed_page_field=table.page.next_page_number %}"
                hx-trigger="revealed"
                hx-target="closest tr"
                hx-swap="afterend"
                {# Include current filters in the next page request #}
                hx-include="form.filter-form">
                
                {% for column, cell in row.items %}
                    <td {{ column.attrs.td.as_html }}>{{ cell }}</td>
                {% endfor %}
            </tr>
        {% else %}
            {# Standard Row #}
            <tr {{ row.attrs.as_html }}>
                {% for column, cell in row.items %}
                    <td {{ column.attrs.td.as_html }}>{{ cell }}</td>
                {% endfor %}
            </tr>
        {% endif %}
    {% endfor %}

    {# "No More Samples" Indicator #}
    {% if not table.page.has_next %}
    <tr class="end-of-list-indicator">
        <td colspan="{{ table.columns|length }}" class="text-center text-muted p-4">
            <em>No more samples available</em>
        </td>
    </tr>
    {% endif %}
</tbody>

The "Counters" Pattern (OOB Swap)
To update the "Showing 50 of 1,200 samples" text (which usually lives above the table) without re-rendering the whole page, use HTMX Out-of-Band (OOB) Swaps.
In your Partial Template (at the bottom):

<div id="table-counts" hx-swap-oob="true">
    Showing {{ table.page.end_index }} of {{ table.paginator.count }} samples
</div>

Note: This div must exist in the main parent page with id="table-counts".

--------------------------------------------------------------------------------
2. Dropdown Implementation Strategy
Standard HTML <select> elements cannot easily infinite scroll. You must build a Server-Driven Dropdown using a hidden input and a scrollable <ul>.
The Component Structure
1. Hidden Input: Stores the actual selected ID (e.g., gene_id).
2. Search Input: hx-trigger="keyup changed delay:500ms" to filter options.
3. Results Container: A scrollable div (max-height) containing the <ul>.
The Dropdown Template

<div class="dropdown-container" x-data="{ open: false }">
    <!-- Search/Trigger -->
    <input type="text" 
           placeholder="Search Genes..." 
           @focus="open = true"
           hx-get="{% url 'gene_search' %}" 
           hx-trigger="keyup changed delay:500ms, focus" 
           hx-target="#gene-results">

    <!-- Results List -->
    <ul id="gene-results" 
        class="dropdown-menu show" 
        x-show="open" 
        @click.outside="open = false"
        style="max-height: 200px; overflow-y: auto;">
        
        <!-- Content loaded via HTMX -->
        {% include "partials/gene_options.html" %}
    </ul>
</div>

The Option Partial (partials/gene_options.html)
Same logic as the table: put the trigger on the last <li>.

{% for gene in page_obj %}
    {% if forloop.last and page_obj.has_next %}
        <li class="dropdown-item" 
            hx-get="{% url 'gene_search' %}?page={{ page_obj.next_page_number }}&q={{ request.GET.q }}"
            hx-trigger="revealed" 
            hx-swap="afterend">
            {{ gene.symbol }}
        </li>
    {% else %}
        <li class="dropdown-item" 
            @click="selectGene('{{ gene.id }}', '{{ gene.symbol }}')">
            {{ gene.symbol }}
        </li>
    {% endif %}
{% endfor %}

{% if not page_obj.has_next %}
    <li class="dropdown-item disabled text-muted">No more genes</li>
{% endif %}

<!-- Dynamic Counter Update (OOB) -->
<span id="gene-count-badge" hx-swap-oob="true" class="badge">
    {{ page_obj.paginator.count }} found
</span>

3. Checklist for the Agent
When implementing this, you must verify:
1. [ ] Pagination context: Is page_obj or table correctly paginated in the view?
2. [ ] Preserve Filters: Does the hx-get on the "Load More" row include current active filters (using hx-include or querystring tag)?
3. [ ] OOB Swaps: Are the counters defined with unique IDs in the main template so hx-swap-oob can find them?
4. [ ] Feedback: Does the "No more samples" message appear only when !has_next?


### Key Technical Explanations [1-4]

1.  **Infinite Scroll Mechanism**: We utilize the `hx-trigger="revealed"` attribute on the *last element* of the current result set. When the user scrolls this element into view, HTMX automatically fires a GET request for the next page [2].
2.  **Updating Counters (OOB)**: Since HTMX usually swaps the *target* (the table rows), we cannot easily update a counter sitting *above* the table in the same request using standard swaps. The solution is **Out-of-Band (OOB) Swaps** [3]. By including an element with `hx-swap-oob="true"` and a matching ID in the response, HTMX updates that element anywhere on the DOM, allowing us to keep the "Showing 100 of 5000" text perfectly in sync with the infinite scroll.
3.  **Dropdown Complexity**: Infinite scroll inside a standard `<select>` is not natively possible. The Skill mandates a "Custom Dropdown" pattern using Alpine.js for the open/close state and HTMX for the list rendering, effectively treating the dropdown options exactly like table rows [2].
