---
trigger: always_on
---

---
description: Security standards for handling Patient Identifiable Information (PII) and Clinical Data.
globs: "**/*.py", "**/*.html"
---

# Security & PII Guardrails

This application handles sensitive clinical data. Security compliance is mandatory.

## PII Encryption
- **Storage:** Never store PII (e.g., `Individual.full_name`, `tc_identity`) in plain text.
- **Implementation:** Use `encrypted_model_fields` (AES-256) for all sensitive model fields.
- **Audit Logging:** Any view or API that decrypts PII must generate an audit log entry.

## UI Reveal Patterns
- **Mask by Default:** Render sensitive fields masked (e.g., `***-**-1234`) in initial table views.
- **Click-to-Reveal:** Use HTMX to securely fetch the cleartext value only upon user request.
  ```html
  <span id="ssn-wrapper">
      ***-**-**** 
      <button hx-get="{% url 'reveal_pii' id %}" hx-target="#ssn-wrapper">Reveal</button>
  </span>

Web Security Configuration
• Headers: Ensure CSRF_COOKIE_SECURE = True and SESSION_COOKIE_SECURE = True.
• Untrusted Inputs: Never use user input directly in hx-target or hx-trigger logic.
• Routes: Only call routes you control (relative URLs).
Reference
• HTMX Security: https://htmx.org/essays/web-security-basics-with-htmx/
• Django Security: https://docs.djangoproject.com/en/6.0/topics/security/