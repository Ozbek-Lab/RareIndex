---
name: style-with-daisyui
description: Generates UI components (Modals, Tables, Alerts, Forms) using daisyUI semantic classes for Tailwind CSS.
---

# Style with daisyUI

Use this skill when the user asks to "make it look good", "add a modal", "style the table", or "add a loading spinner".
Make sure to check https://daisyui.com/llms.txt for the latest information.


## Philosophy
We use daisyUI to keep HTML clean. Instead of 50 Tailwind utility classes, we use semantic component classes (e.g., `btn btn-primary`) modified by utilities where necessary.

## Component Patterns

### 1. Data Tables (django-tables2 integration)
When using `django-tables2`, apply daisyUI classes via the `Table.Meta.attrs`.

**Python Definition:**
```python
class VariantTable(tables.Table):
    class Meta:
        # 'table' = daisyUI base
        # 'table-zebra' = striped rows
        # 'table-pin-rows' = sticky header
        attrs = {"class": "table table-zebra table-pin-rows table-sm"}

Template HTML: Ensure the container handles overflow for sticky headers:

<div class="overflow-x-auto h-96"> <!-- h-96 enables vertical scrolling for sticky header -->
    {% render_table table %}
</div>

2. HTMX Loading Indicators
Use daisyUI loading classes for hx-indicator.
Pattern:

<!-- Button with internal spinner -->
<button class="btn btn-primary" hx-post="..." hx-indicator="#spinner">
    <span id="spinner" class="loading loading-spinner loading-sm htmx-indicator"></span>
    Save
</button>

<!-- Global Overlay Spinner -->
<div id="global-loader" class="htmx-indicator fixed inset-0 bg-black/50 z-50 flex items-center justify-center">
    <span class="loading loading-dots loading-lg text-primary"></span>
</div>

3. Modals (Alpine.js + daisyUI)
Do not use the daisyUI "checkbox hack". Use the <dialog> element controlled by Alpine.js for better accessibility and state management.
Pattern:

<dialog id="generic_modal" class="modal" x-data="{ open: false }" :class="{ 'modal-open': open }" @open-modal.window="open = true" @close-modal.window="open = false">
    <div class="modal-box">
        <h3 class="font-bold text-lg">Hello!</h3>
        <div id="modal-content">
            <!-- HTMX injects content here -->
        </div>
        <div class="modal-action">
            <button class="btn" @click="open = false">Close</button>
        </div>
    </div>
    <!-- Backdrop click to close -->
    <form method="dialog" class="modal-backdrop">
        <button @click="open = false">close</button>
    </form>
</dialog>

4. Alerts & Toasts (OOB Swaps)
Use toast for ephemeral notifications triggered by HTMX OOB swaps.
Template (Base Layout):

<div class="toast toast-end toast-bottom z-50">
    <!-- Target for OOB swaps -->
    <div id="toast-container"></div>
</div>

Response Partial (HTMX OOB):

<div id="toast-container" hx-swap-oob="beforeend">
    <div x-data="{ show: true }" x-show="show" x-init="setTimeout(() => show = false, 3000)" class="alert alert-success">
        <span>Data saved successfully.</span>
    </div>
</div>

5. Forms
Style Django form widgets using widget_tweaks or manual rendering with daisyUI classes.
Django Widget
	
daisyUI Class
	
Example
TextInput
	
input input-bordered
	
<input class="input input-bordered w-full" ...>
Select
	
select select-bordered
	
<select class="select select-bordered" ...>
Checkbox
	
checkbox checkbox-primary
	
<input type="checkbox" class="checkbox" ...>
FileInput
	
file-input file-input-bordered
	
<input type="file" class="file-input" ...>
Configuration
Ensure tailwind.config.js includes the daisyUI plugin and your theme preferences.

module.exports = {
  // ...
  plugins: [require("daisyui")],
  daisyui: {
    themes: ["light", "dark", "corporate"], // 'corporate' is good for LIMS
  },
}


### Technical Note on the "Modal" Pattern
The skill explicitly advises **against** the pure CSS "checkbox hack" often seen in daisyUI examples (Source [1]). Instead, it combines daisyUI's styling (`.modal`, `.modal-box`) with **Alpine.js** (`x-data`, `:class`) and **HTMX**. This aligns with your **Rule #2 (Locality of Behaviour)** and **Rule #5 (Alpine.js Reactivity)**, ensuring modals can be opened programmatically (e.g., after an HTMX request) rather than just by CSS pseudo-selectors.