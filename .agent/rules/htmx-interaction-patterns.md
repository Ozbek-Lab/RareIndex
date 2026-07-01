---
trigger: always_on
---

---
description: Standard patterns for HTMX table interactions, filtering, and editing.
globs: "**/*.html", "**/views.py"
---

# HTMX Interaction Patterns

## 0. HTMX
- Always prefer declerative HTMX patterns, instead of writing custom javascript.

## 1. Edit Row Pattern
- To edit a record in a table, replace the specific `<tr>` with a form row.
- **View:** Return the form partial on GET; return the read-only row partial on successful POST.
- **Attributes:** Use `hx-target="closest tr"` and `hx-swap="outerHTML"`.

## 2. Active Search
- For global filtering, trigger requests as the user types.
- **Pattern:** `hx-trigger="keyup delay:500ms changed"`.
- **Indicator:** Always use `hx-indicator` to show a loading spinner.

## 3. Out-of-Band (OOB) Swaps
- Use `hx-swap-oob="true"` to update side effects (e.g., updating a "Total Count" badge in the navbar when a row is added).

## 4. Modal Handling
- Load modal content dynamically via `hx-get`.
- Place the modal container in the base template and target it: `hx-target="#modal-container"`.

## Reference
- https://htmx.org/reference/