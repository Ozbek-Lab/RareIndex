---
name: generate-django-tests
description: Generates Django TestCases to validate HTMX views, table filtering, and partial rendering.
---

# Generate Django Tests

- Use this skill when the user asks to "write tests for [View/Feature]", "test the table filters", or "ensure HTMX works".
- When you encounter an error while running the server, you must add a test to prevent the error from happening again.
- When you implement a new feature, test it using the browser and then write tests for it.
- When you add a new feature, you must add a test to ensure the feature works as expected.
- When you encounter an error while running the tests, you must fix the error and run the tests again.


## Testing Strategy
You must write tests that strictly differentiate between **Standard Requests** (Full Page) and **HTMX Requests** (Partial Content).

## 1. The HTMX Test Pattern
When testing HTMX views, you must manually inject the `HX-Request` header.

```python
# test_views.py pattern
from django.test import TestCase, Client
from django.urls import reverse
from .factories import SampleFactory  # Use the factory skill if available

class SampleListViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('sample_list')
        self.samples = SampleFactory.create_batch(10)

    def test_full_page_load(self):
        """Standard GET should return the full page with base template."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<html")  # Ensure full page
        self.assertContains(response, "table-container")

    def test_htmx_partial_load(self):
        """HTMX GET should return ONLY the table partial, not the full page."""
        headers = {'HTTP_HX_REQUEST': 'true'}
        response = self.client.get(self.url, **headers)
        
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html")  # Ensure NO full page
        self.assertContains(response, "<tr", count=10) # Verify rows exist

2. Testing Filters & Search
You must verify that passing GET parameters actually reduces the queryset in the HTML response.

    def test_filter_by_status(self):
        """Ensure query params filter the table rows."""
        # Setup: 1 active, 9 archived
        SampleFactory(status='active')
        SampleFactory.create_batch(9, status='archived')
        
        # Act: Filter for 'active' via HTMX
        headers = {'HTTP_HX_REQUEST': 'true'}
        response = self.client.get(self.url, {'status': 'active'}, **headers)
        
        # Assert: Should see 1 row, not 10
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['table'].data), 1)

3. Testing Infinite Scroll (The "Revealed" Pattern)
If the view implements infinite scroll, you must verify pagination context.

    def test_infinite_scroll_pagination(self):
        """Requesting page 2 should return rows and indicate if more pages exist."""
        SampleFactory.create_batch(30) # Assuming paginate_by = 25
        
        headers = {'HTTP_HX_REQUEST': 'true'}
        response = self.client.get(self.url, {'page': 2}, **headers)
        
        self.assertEqual(response.status_code, 200)
        # Verify we got the remaining 5 items
        self.assertEqual(len(response.context['table'].data), 5)
        # Verify the "No more samples" indicator is present if it's the last page
        self.assertContains(response, "No more samples")

4. Testing Inline Edits (HTMX POST)
Test the state change and the HTML swap return.

    def test_inline_status_update(self):
        sample = SampleFactory(status='pending')
        url = reverse('update_status', args=[sample.id])
        
        headers = {'HTTP_HX_REQUEST': 'true'}
        data = {'status': 'complete'}
        
        # POST the change
        response = self.client.post(url, data, **headers)
        
        # Assert DB change
        sample.refresh_from_db()
        self.assertEqual(sample.status, 'complete')
        
        # Assert Response is the updated row (partial)
        self.assertContains(response, "complete")
        self.assertContains(response, f'id="row-{sample.id}"')

5. Security Checks
Always add a test to ensure PII is masked by default if the model is Individual.

    def test_pii_is_masked_by_default(self):
        ind = IndividualFactory(full_name="John Doe")
        response = self.client.get(self.url)
        self.assertNotContains(response, "John Doe")
        self.assertContains(response, "***-**-****")


### Key Technical Insights for the Agent
1.  **`HTTP_HX_REQUEST`**: The Django test client uses WSGI header naming conventions. You must pass `'HTTP_HX_REQUEST': 'true'` in the `**headers` argument (or `**extra` in older Django versions) for `request.htmx` to resolve to `True` [1-3].
2.  **`assertNotContains(response, "<html")`**: This is the most reliable way to prove you are returning a **partial** (HTML fragment) rather than a full page, which prevents the "Double Header" UI bug [2, 4].
3.  **Context Assertion**: While `assertContains` checks the HTML string, inspecting `response.context['table'].data` is a robust way to verify that `django-filter` successfully narrowed down the database query [5, 6].