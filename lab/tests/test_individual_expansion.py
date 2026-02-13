from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from lab.models import Individual, Status, Project, Sample, Test, Pipeline, PipelineType, SampleType, TestType

class IndividualExpansionTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.client = Client()
        self.client.force_login(self.user)
        
        self.status = Status.objects.create(name="Active", created_by=self.user)
        self.individual = Individual.objects.create(
            full_name="John Doe",
            status=self.status,
            created_by=self.user,
            sex="male"
        )
        
        # Create related data
        self.sample_type = SampleType.objects.create(name="Blood", created_by=self.user)
        self.sample = Sample.objects.create(
            individual=self.individual, 
            sample_type=self.sample_type, 
            status=self.status,
            created_by=self.user,
            isolation_by=self.user
        )
        
        self.test_type = TestType.objects.create(name="WGS", created_by=self.user)
        self.test = Test.objects.create(
            sample=self.sample,
            test_type=self.test_type,
            status=self.status,
            created_by=self.user
        )
        
        self.pipeline_type = PipelineType.objects.create(name="Dragen", version="1.0", created_by=self.user)
        self.pipeline = Pipeline.objects.create(
            test=self.test,
            type=self.pipeline_type,
            status=self.status,
            performed_date="2023-01-01",
            performed_by=self.user,
            created_by=self.user
        )

    def test_list_view_uses_expandable_template(self):
        url = reverse("lab:individual_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Check if the table class uses the correct template (hard to check template name directly from response context with django-tables2 sometimes, 
        # but we can check if the rendered HTML contains specific expandable logic)
        self.assertContains(response, 'x-data="{ expanded: false }"')
        self.assertContains(response, 'hx-get=')

    def test_detail_view_renders_correctly(self):
        url = reverse("lab:individual_detail", args=[self.individual.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # Check for tab headers
        self.assertContains(response, "Info")
        self.assertContains(response, "Phenotype")
        self.assertContains(response, "Samples & Tests")
        
        # Check for content presence
        self.assertContains(response, "John Doe") # Masked but maybe present in context/revealed logic if we checked logic
        # Actually it's masked as ***** in default view without special reveal call
        self.assertContains(response, "*****") 
        
        # Check for sample info
        self.assertContains(response, "Blood")
        
        # Check for analysis info
        self.assertContains(response, "Dragen")
