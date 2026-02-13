from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from variant.models import Variant
from lab.models import Task, Status, Project, Individual

User = get_user_model()

class VariantTaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.status = Status.objects.create(name="Open", color="blue", created_by=self.user)
        self.individual = Individual.objects.create(
            full_name="Test Individual",
            status=self.status,
            created_by=self.user
        )
        self.variant = Variant.objects.create(
            chromosome="chr1",
            start=100,
            end=101,
            individual=self.individual,
            created_by=self.user
        )

    def test_create_task_for_variant(self):
        """Test that a task can be created and associated with a variant."""
        task = Task.objects.create(
            title="Investigate Variant",
            description="Check for pathogenicity",
            content_object=self.variant,
            assigned_to=self.user,
            created_by=self.user,
            status=self.status
        )
        
        self.assertEqual(task.content_object, self.variant)
        self.assertIn(task, self.variant.tasks.all())
        self.assertEqual(self.variant.tasks.count(), 1)

    def test_variant_tasks_relation(self):
        """Test the reverse relation from variant to tasks."""
        task1 = Task.objects.create(
            title="Task 1",
            content_object=self.variant,
            assigned_to=self.user,
            created_by=self.user,
            status=self.status
        )
        task2 = Task.objects.create(
            title="Task 2",
            content_object=self.variant,
            assigned_to=self.user,
            created_by=self.user,
            status=self.status
        )
        
        self.assertEqual(self.variant.tasks.count(), 2)
        self.assertIn(task1, self.variant.tasks.all())
        self.assertIn(task2, self.variant.tasks.all())

    def test_create_task_for_test(self):
        """Test that a task can be created and associated with a test."""
        from lab.models import Test, TestType, Sample, SampleType
        
        test_type = TestType.objects.create(name="WGS", created_by=self.user)
        sample_type = SampleType.objects.create(name="Blood", created_by=self.user)
        sample = Sample.objects.create(
            individual=self.individual,
            sample_type=sample_type,
            status=self.status,
            created_by=self.user,
            isolation_by=self.user
        )
        test = Test.objects.create(
            sample=sample,
            test_type=test_type,
            status=self.status,
            created_by=self.user
        )
        
        task = Task.objects.create(
            title="Investigate Test",
            description="Check QC metrics",
            content_object=test,
            assigned_to=self.user,
            created_by=self.user,
            status=self.status
        )
        
        self.assertEqual(task.content_object, test)
        self.assertIn(task, test.tasks.all())
        self.assertEqual(test.tasks.count(), 1)

    def test_variants_property(self):
        """Test that the variants property returns correct variants for Sample and Test."""
        from lab.models import Test, TestType, Sample, SampleType, Pipeline, PipelineType
        
        # Create Sample and Test
        test_type = TestType.objects.create(name="WGS", created_by=self.user)
        sample_type = SampleType.objects.create(name="Blood", created_by=self.user)
        sample = Sample.objects.create(
            individual=self.individual,
            sample_type=sample_type,
            status=self.status,
            created_by=self.user,
            isolation_by=self.user
        )
        test = Test.objects.create(
            sample=sample,
            test_type=test_type,
            status=self.status,
            created_by=self.user
        )
        
        # Create Pipeline
        pipeline_type = PipelineType.objects.create(name="Variant Calling", created_by=self.user)
        pipeline = Pipeline.objects.create(
            test=test,
            type=pipeline_type,
            status=self.status,
            performed_date="2023-01-01",
            performed_by=self.user,
            created_by=self.user
        )
        
        # Create Variant associated with Pipeline
        variant = Variant.objects.create(
            chromosome="chr2",
            start=200,
            end=201,
            individual=self.individual,
            pipeline=pipeline,
            created_by=self.user
        )
        
        # Verify Sample.variants
        self.assertIn(variant, sample.variants)
        self.assertEqual(sample.variants.count(), 1)
        
        # Verify Test.variants
        self.assertIn(variant, test.variants)
        self.assertEqual(test.variants.count(), 1)
