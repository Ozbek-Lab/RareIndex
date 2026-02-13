---
trigger: always_on
---

---
description: Standards for using Django 6 template partials to support HTMX.
globs: "**/*.html", "**/views.py"
---

# Django Template Partials

Avoid creating separate files for every HTML fragment. Use `django-template-partials` which is already included in Django 6.0. We don't need to install it from pip.

## Implementation
1. **Define Partial:** Wrap reusable fragments (rows, forms) in `{% partialdef name %}` ... `{% endpartialdef %}`.
2. **View Logic:**
   - Detect HTMX requests: `if request.htmx:`
   - Render *only* the partial: `return render(request, "template.html#name", context)`.
3. **Usage:**
   - Include the partial in the main page render using `{% partial name %}` to ensure initial load consistency.

## Prevention of "Double Headers"
- Never extend the base template inside a response meant for an HTMX target. Explicitly selecting the partial prevents re-rendering the `<html>` and `<body>` tags.

## Reference
- **Django Template Partials:** https://github.com/carltongibson/django-template-partials