from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from lab.models import Family

class FamilyPickerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client = Client()
        self.client.force_login(self.user)
        
        # Create some families
        for i in range(15):
            Family.objects.create(family_id=f"FAM{i:03d}", description=f"Family {i}")

    def test_family_search_response(self):
        url = reverse('lab:family_search')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "FAM000")
        
        # Test pagination (should show 10 items)
        self.assertContains(response, "hx-trigger=\"intersect once\"") 

    def test_family_search_query(self):
        url = reverse('lab:family_search')
        response = self.client.get(url, {'q': 'FAM005'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "FAM005")
        self.assertNotContains(response, "FAM001")
