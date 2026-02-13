from django.test import TestCase, Client
from django.urls import reverse
from lab.models import Individual, Status

class ResetAllTest(TestCase):
    def setUp(self):
        self.status = Status.objects.create(name="Active")
        self.individual = Individual.objects.create(
            individual_id="IND_RESET",
            full_name="Test User Reset",
            status=self.status,
            sex="Male"
        )
        self.client = Client()
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client.login(username='testuser', password='password')
        self.url = reverse('lab:individual_list')

    def test_reset_all_returns_full_page(self):
        # Simulate "Reset All" button click which targets body
        headers = {'HTTP_HX_REQUEST': 'true', 'HTTP_HX_TARGET': 'body'}
        response = self.client.get(self.url, **headers)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Should return full page (check for html/body tags or base template content)
        self.assertIn('<html', content)
        self.assertIn('<body', content)
        self.assertIn('IND_RESET', content) # Should show data

    def test_filter_returns_partial(self):
        # Simulate Filter request
        headers = {'HTTP_HX_REQUEST': 'true', 'HTTP_HX_TARGET': 'individual-table-container'}
        response = self.client.get(self.url, {'status': self.status.id}, **headers)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Should be partial (no html/body tags)
        self.assertNotIn('<html', content)
        self.assertNotIn('<body', content)
        self.assertIn('IND_RESET', content)
