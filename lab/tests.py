from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from .models import Individual, Sample, Status, SampleType, Family, Institution

class LabUIViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client.login(username='testuser', password='password')
        
        # Setup basic data
        self.status = Status.objects.create(name="Active", created_by=self.user)
        self.sample_type = SampleType.objects.create(name="Blood", created_by=self.user)
        self.institution = Institution.objects.create(name="Test Inst")
        
        self.individual = Individual.objects.create(
            full_name="Test Individual",
            status=self.status,
            created_by=self.user
        )
        self.sample = Sample.objects.create(
            individual=self.individual,
            sample_type=self.sample_type,
            status=self.status,
            created_by=self.user
        )

    def test_dashboard_view(self):
        url = reverse('lab:dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "RareIndex")
        self.assertContains(response, "Individuals")
        self.assertContains(response, "Samples")

    def test_individual_list_full_page(self):
        url = reverse('lab:individual_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<html") # Full page
        self.assertContains(response, "individual-table-container")
        self.assertContains(response, "Test Individual")

    def test_individual_list_htmx(self):
        url = reverse('lab:individual_list')
        headers = {'HTTP_HX_REQUEST': 'true'}
        response = self.client.get(url, **headers)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html") # Partial
        self.assertContains(response, "individual-table-container")
        self.assertContains(response, "Test Individual")

    def test_individual_filter(self):
        url = reverse('lab:individual_list')
        headers = {'HTTP_HX_REQUEST': 'true'}
        response = self.client.get(url, {'search': 'Test Individual'}, **headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['table'].data), 1)
        
        response = self.client.get(url, {'search': 'NonExistent'}, **headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['table'].data), 0)

    def test_sample_list_full_page(self):
        url = reverse('lab:sample_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<html") # Full page
        self.assertContains(response, "sample-table-container")

    def test_sample_list_htmx(self):
        url = reverse('lab:sample_list')
        headers = {'HTTP_HX_REQUEST': 'true'}
        response = self.client.get(url, **headers)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html") # Partial
        self.assertContains(response, "sample-table-container")
        
