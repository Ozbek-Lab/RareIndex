---
trigger: always_on
---

---
description: Enforces the Locality of Behaviour (LoB) principle for all frontend code.
globs: "**/*.html"
---

# Locality of Behaviour (LoB)

Follow the "Locality of Behaviour" principle as defined by Carson Gross. The behaviour of a unit of code should be as obvious as possible by looking only at that unit of code.

## Implementation Guidelines

### 1. Inline HTMX Attributes
- Place `hx-*` attributes directly on the triggering element.
- **Bad:** Using jQuery `$('#btn').on('click', ...)` or separate JS event listeners.
- **Good:** `<button hx-get="/clicked" hx-swap="outerHTML">`

### 2. Inline Alpine.js State
- Define UI state locally using `x-data` directly on the HTML element.
- Avoid creating separate `.js` files for small interactions like toggles or modals.
- **Example:**
  ```html
  <div x-data="{ open: false }">
      <button @click="open = !open">Toggle</button>
      <div x-show="open">Content</div>
  </div>

3. Trade-offs
• It is acceptable to violate DRY (Don't Repeat Yourself) to preserve LoB.
• Do not abstract standard HTMX patterns into complex wrapper functions unless they are used globally.
Reference
• The LoB Principle: https://htmx.org/essays/locality-of-behaviour/