---
name: secure-pii-reveal
description: Implements a secure "mask by default, click to reveal" pattern for sensitive PII fields.
---

# Secure PII Reveal Pattern

Use this skill when handling sensitive fields like `full_name`, `ssn`, `tc_identity`, or `birth_date`.

## Security Mandate
**NEVER** render these fields in plain text on initial page load.

## Implementation Steps

### 1. The Template Pattern
Render the field masked by default. Use an HTMX trigger to fetch the real value.

```html
<span id="pii-{{ object.id }}" class="pii-masked">
    ***-**-****
    <button class="btn-xs"
            hx-get="{% url 'reveal_pii' object.id 'field_name' %}"
            hx-target="#pii-{{ object.id }}"
            hx-swap="innerHTML">
        Reveal
    </button>
</span>

2. The Reveal View
Create a secure endpoint that:
1. Authenticates: Ensures user has view_sensitive_data permission.
2. Logs Access: Records an AuditLog entry (User X revealed Field Y on Object Z).
3. Decrypts: Accesses the EncryptedField to get the cleartext value.
4. Renders: Returns only the cleartext value (not a full page).
3. Alpine.js Auto-Hide (Optional)
Add Alpine.js to automatically re-mask the data after 30 seconds to prevent "shoulder surfing" in the lab.

<span x-data="{ shown: true }" x-init="setTimeout(() => shown = false, 30000)" x-show="shown">
    {{ cleartext_value }}
</span>
