---
trigger: always_on
---

---
description: Enforces the PETAL stack (Python, Django, HTMX, Alpine.js) and forbids heavy frontend frameworks.
globs: "**/*.py", "**/*.html", "**/*.js"
---

# Technical Stack Enforcement
You are an expert Django developer building a Rare Disease Clinical LIMS. You must strictly adhere to the PETAL stack architecture.

## Core Technologies
- **Backend:** Django 6.0 (Python 3.14).
- **Frontend Interaction:** HTMX for server interaction. Always stay back from writing custom javascript.
- **Frontend Reactivity:** Alpine.js for client-side UI state. Always stay back from writing custom javascript.
- **Data Tables:** `django-tables2` for rendering, sorting, and pagination.
- **Filtering:** `django-filter` for dynamic querysets.
- **Templating:** Django Template Language (DTL) with `django-template-partials`.
- **CSS:** Use https://github.com/saadeghi/daisyui for compenent library.

## Prohibited Technologies
- **NO React, Vue, Angular, Svelte, or HTMX-json-enc.**
- **NO DRF Serializers** for UI views (return HTML partials, not JSON).
- **NO Node.js build steps** unless specifically requested for CSS processing (Tailwind).

## Documentation Links
- **Django Tables2:** https://django-tables2.readthedocs.io/en/latest/
- **Django Filter:** https://django-filter.readthedocs.io/en/stable/
- **HTMX:** https://htmx.org/docs/

## Package management
- Use uv for package management.
- use the .venv for the environmet.
- for the browser tests use 127.0.0.1:8000