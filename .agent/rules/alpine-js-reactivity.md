---
trigger: always_on
---

---
description: Guidelines for using Alpine.js for client-side interactivity.
globs: "**/*.html"
---

# Alpine.js Reactivity
- Always prefer declerative alpine.js patterns.

Use Alpine.js strictly for client-side UI logic that does not require a server round-trip.

## Scope
- **Allowed:** Toggling visibility (`x-show`), masking inputs, switching tabs, closing alerts, simple client-side validation.
- **Forbidden:** Business logic, complex data manipulation, or replacing server-side HTML rendering.

## Integration with HTMX
- Alpine and HTMX must coexist. HTMX swaps DOM elements; Alpine initializes behavior on new elements.
- **State Persistence:** Use `x-data` on container elements so state persists during partial child swaps if necessary.
- **Events:** Use `hx-on::after-request` to dispatch events that Alpine listens for (e.g., closing a modal after a successful save).

## Reference
- **Alpine Docs:** https://alpinejs.dev/start-here