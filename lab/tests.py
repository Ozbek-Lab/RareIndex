from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from .models import (
    CrossIdentifier,
    IdentifierType,
    Individual,
    Project,
    ProjectMembership,
    Sample,
    Status,
    SampleType,
    Family,
    Institution,
)


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class LabUIViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='password')
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Individual),
                codename="view_individual",
            ),
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Sample),
                codename="view_sample",
            ),
        )
        self.client.login(username='testuser', password='password')
        
        # Setup basic data
        self.status = Status.objects.create(name="Active", created_by=self.user)
        self.primary_type = IdentifierType.objects.create(
            name="Primary",
            use_priority=1,
            created_by=self.user,
        )
        self.sample_type = SampleType.objects.create(name="Blood", created_by=self.user)
        self.institution = Institution.objects.create(name="Test Inst", created_by=self.user)
        
        self.individual = Individual.objects.create(
            full_name="Test Individual",
            created_by=self.user
        )
        CrossIdentifier.objects.create(
            individual=self.individual,
            id_type=self.primary_type,
            id_value="TEST-1",
            created_by=self.user,
        )
        self.individual.statuses.add(self.status)
        self.project = Project.objects.create(name="Visible Project", created_by=self.user)
        self.project.individuals.add(self.individual)
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ProjectMembership.Role.VIEWER,
            created_by=self.user,
        )
        self.sample = Sample.objects.create(
            individual=self.individual,
            sample_type=self.sample_type,
            created_by=self.user
        )
        self.sample.statuses.add(self.status)

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
        self.assertContains(response, "TEST-1")

    def test_individual_list_htmx(self):
        url = reverse('lab:individual_list')
        headers = {
            'HTTP_HX_REQUEST': 'true',
            'HTTP_HX_TARGET': 'individual-table-container',
        }
        response = self.client.get(url, **headers)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html") # Partial
        self.assertContains(response, "individual-table-container")
        self.assertContains(response, "TEST-1")

    def test_individual_filter(self):
        url = reverse('lab:individual_list')
        headers = {
            'HTTP_HX_REQUEST': 'true',
            'HTTP_HX_TARGET': 'individual-table-container',
        }
        response = self.client.get(url, {'search': 'TEST-1'}, **headers)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "TEST-1")
        
        response = self.client.get(url, {'search': 'NonExistent'}, **headers)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "TEST-1")

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
        
