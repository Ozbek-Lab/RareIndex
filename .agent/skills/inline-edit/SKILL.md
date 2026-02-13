---
name: implement-inline-edit
description: Refactors a table row to support inline editing using the HTMX "Edit Row" pattern.
---

# Implement Inline Edit

Use this skill when the user wants to "edit [Field] in the table" or "change status without leaving the page".

## Core Concept
We swap a read-only `<tr>` with a form-containing `<tr>` and back again.

## Implementation Steps

### 1. View Actions
Create two specific view methods (or a separate View class):
1.  **`edit_row` (GET):** Returns the HTML fragment for the row in "edit mode" (inputs).
2.  **`save_row` (POST):** Validates data. 
    *   *Success:* Returns the HTML fragment for the row in "read-only mode" (text).
    *   *Failure:* Returns the "edit mode" row again with validation errors.

### 2. Template Fragments (Django Partials)
Define two partials within the same template file using `django-template-partials`.

**Partial 1: Read-Only Row**
```html
{% partialdef row_display %}
<tr id="row-{{ object.id }}">
    <td>{{ object.name }}</td>
    <td>{{ object.status }}</td>
    <td>
        <button hx-get="{% url 'edit_row' object.id %}" 
                hx-target="closest tr" 
                hx-swap="outerHTML">
            Edit
        </button>
    </td>
</tr>
{% endpartialdef %}

Partial 2: Editing Row

{% partialdef row_edit %}
<tr id="row-{{ object.id }}" class="editing">
    <td>{{ form.name }}</td>
    <td>{{ form.status }}</td>
    <td>
        <button hx-post="{% url 'save_row' object.id %}" 
                hx-target="closest tr" 
                hx-swap="outerHTML"
                hx-include="closest tr">
            Save
        </button>
        <button hx-get="{% url 'row_display' object.id %}" 
                hx-target="closest tr" 
                hx-swap="outerHTML">
            Cancel
        </button>
    </td>
</tr>
{% endpartialdef %}

3. Alpine.js Integration (Optional)
If the edit requires complex UI (like a dependent dropdown), use Alpine inside the row_edit partial: <tr x-data="{ status: '{{ object.status }}' }">...</tr>