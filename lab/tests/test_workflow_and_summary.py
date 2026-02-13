from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from lab.models import Individual, Sample, Test, Pipeline, Status, SampleType, TestType, PipelineType
from datetime import date

class WorkflowAndSummaryTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.client = Client()
        self.client.login(username="testuser", password="password")

        # Grant permissions
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        for model in [Individual, Sample, Test, Pipeline]:
            content_type = ContentType.objects.get_for_model(model)
            permission = Permission.objects.get(
                codename=f"change_{model.__name__.lower()}",
                content_type=content_type,
            )
            self.user.user_permissions.add(permission)
        self.user.save()
        
        # Setup Statuses
        self.status = Status.objects.create(name="Active", color="green", created_by=self.user)
        
        # Setup Types
        self.sample_type = SampleType.objects.create(name="Blood", created_by=self.user)
        self.test_type = TestType.objects.create(name="WGS", created_by=self.user)
        self.pipeline_type = PipelineType.objects.create(name="Rare Disease", version="1.0", created_by=self.user)
        
        # Setup Individual
        self.individual = Individual.objects.create(
            full_name="Test Individual",
            status=self.status,
            created_by=self.user
        )
        
        # Setup Hierarchy
        self.sample = Sample.objects.create(
            individual=self.individual,
            sample_type=self.sample_type,
            status=self.status,
            created_by=self.user,
            isolation_by=self.user,
            receipt_date=date.today()
        )
        self.test = Test.objects.create(
            sample=self.sample,
            test_type=self.test_type,
            status=self.status,
            created_by=self.user
        )
        self.pipeline = Pipeline.objects.create(
            test=self.test,
            type=self.pipeline_type,
            status=self.status,
            performed_date=date.today(),
            performed_by=self.user,
            created_by=self.user
        )

    def test_workflow_tab_renders(self):
        """Test that the workflow tab renders the hierarchy correctly"""
        # Render the partial directly
        response = self.client.get(reverse('lab:individual_detail', args=[self.individual.pk]))
        self.assertEqual(response.status_code, 200)
        
        # Check context or content if possible. 
        self.assertContains(response, "Blood")
        self.assertContains(response, "WGS")
        self.assertContains(response, "Rare Disease")
        self.assertContains(response, "v1.0")

    def test_clinical_summary_edit_flow(self):
        """Test the inline edit flow for Clinical Summary"""
        # 1. Check Display Mode (GET detail)
        response = self.client.get(reverse('lab:individual_clinical_summary_display', args=[self.individual.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Clinical Summary")
        
        # 2. Check Edit Mode (GET edit)
        response = self.client.get(reverse('lab:individual_clinical_summary_edit', args=[self.individual.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="diagnosis"')
        
        # 3. Save Changes (POST save)
        new_diagnosis = "New Diagnosis 123"
        response = self.client.post(reverse('lab:individual_clinical_summary_save', args=[self.individual.pk]), {
            "diagnosis": new_diagnosis,
            "icd11_code": "CODE123",
            "is_affected": "on", # checkbox
            "diagnosis_date": "2023-01-01"
        })
        self.assertEqual(response.status_code, 200)
        
        # Verify DB update
        self.individual.refresh_from_db()
        self.assertEqual(self.individual.diagnosis, new_diagnosis)
        
    def test_status_update(self):
        """Test updating status via HTMX"""
        from django.contrib.contenttypes.models import ContentType
        new_status = Status.objects.create(name="Completed", color="blue", created_by=self.user)
        ct_id = ContentType.objects.get_for_model(Sample).id
        
        url = reverse('lab:update_status', args=[ct_id, self.sample.id, new_status.id])
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 200)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.status, new_status)
        
        # Verify response contains the new status name and color
        self.assertContains(response, "Completed")
        self.assertContains(response, "blue")

    def test_individual_status_update(self):
        """Test updating individual status via HTMX"""
        from django.contrib.contenttypes.models import ContentType
        new_status = Status.objects.create(name="Solved", color="purple", created_by=self.user)
        ct_id = ContentType.objects.get_for_model(Individual).id
        
        url = reverse('lab:update_status', args=[ct_id, self.individual.id, new_status.id])
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, 200)
        self.individual.refresh_from_db()
        self.assertEqual(self.individual.status, new_status)
        
        # Verify response contains the new status name and color
        self.assertContains(response, "Solved")
        self.assertContains(response, "purple")
        
        # Verify OOB swap for table row is present and correctly structured
        # The hx-swap-oob should be on the same element that has the ID
        expected_oob = f'hx-swap-oob="true" id="individual-row-status-{self.individual.id}"'
        self.assertContains(response, expected_oob)

    def test_sample_creation(self):
        """Test creating a sample via HTMX modal view"""
        url = reverse('lab:sample_create_modal', args=[self.individual.pk])
        
        # 1. GET should return form
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add New Sample")
        
        # 2. POST should create sample and return workflow tab
        response = self.client.post(url, {
            "individual": self.individual.id,
            "sample_type": self.sample_type.id,
            "status": self.status.id,
            "receipt_date": "2023-01-01",
            "isolation_by": self.user.id,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.individual.samples.count(), 2)
        # Should render workflow content (check for sample ID or type)
        self.assertContains(response, "Blood")

    def test_test_creation(self):
        """Test creating a test via HTMX modal view"""
        url = reverse('lab:test_create_modal', args=[self.sample.pk])
        
        # 1. GET should return form
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add Test for Sample")
        
        # 2. POST should create test and return workflow tab
        response = self.client.post(url, {
            "sample": self.sample.id,
            "test_type": self.test_type.id,
            "status": self.status.id,
            "performed_date": "2023-01-01",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sample.tests.count(), 2)
        self.assertContains(response, "WGS")

    def test_workflow_notes_visibility(self):
        """Test that notes are visible in the workflow tab"""
        from lab.models import Note
        from django.contrib.contenttypes.models import ContentType
        
        # Create an individual note
        Note.objects.create(
            content="Individual Note Text",
            user=self.user,
            content_type=ContentType.objects.get_for_model(Individual),
            object_id=self.individual.id
        )
        
        # Create a sample note
        Note.objects.create(
            content="Sample Note Text",
            user=self.user,
            content_type=ContentType.objects.get_for_model(Sample),
            object_id=self.sample.id
        )
        
        # Render workflow partial (via detail view as it's included there)
        response = self.client.get(reverse('lab:individual_detail', args=[self.individual.pk]))
        self.assertContains(response, "Individual Note Text")
        self.assertContains(response, "Sample Note Text")
