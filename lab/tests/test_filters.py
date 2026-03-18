from django.test import TestCase
from lab.models import Individual, Status, Sample, SampleType, Test as LabTest, TestType, Pipeline, PipelineType, Analysis, AnalysisReport, AnalysisRequestForm, Project
from lab.filters import IndividualFilter
from django.contrib.auth.models import User
import datetime

class IndividualFilterTest(TestCase):
    def setUp(self):
        # Create Users
        self.user = User.objects.create_user(username="testuser", password="password")
        
        from django.contrib.contenttypes.models import ContentType
        ind_ct = ContentType.objects.get_for_model(Individual)
        sample_ct = ContentType.objects.get_for_model(Sample)

        # Create Statuses
        # Individual Statuses
        self.active_status = Status.objects.create(name="Active", content_type=ind_ct, created_by=self.user)
        self.inactive_status = Status.objects.create(name="Inactive", content_type=ind_ct, created_by=self.user)
        
        # Sample Statuses
        self.sample_active_status = Status.objects.create(name="Active", content_type=sample_ct, created_by=self.user)
        self.failed_status = Status.objects.create(name="Failed", content_type=sample_ct, created_by=self.user)
        
        # Create Sample Types
        self.blood_type = SampleType.objects.create(name="Blood", created_by=self.user)
        self.saliva_type = SampleType.objects.create(name="Saliva", created_by=self.user)

        # Create Individuals
        self.ind1 = Individual.objects.create(
            full_name="John Doe", 
            sex="male", 
            is_affected=True,
            is_index=True,
            status=self.active_status,
            created_by=self.user
        )
        self.ind2 = Individual.objects.create(
            full_name="Jane Doe", 
            sex="female", 
            is_affected=False,
            is_index=False,
            status=self.active_status,
            created_by=self.user
        )
        self.ind3 = Individual.objects.create(
            full_name="Inactive User", 
            sex="male", 
            is_affected=True,
            is_index=False,
            status=self.inactive_status,
            created_by=self.user
        )

        # Create Samples
        # Ind1 has Blood (Active)
        Sample.objects.create(
            individual=self.ind1, 
            sample_type=self.blood_type, 
            status=self.sample_active_status, # Use sample specific status
            isolation_by=self.user,
            created_by=self.user
        )
        # Ind2 has Saliva (Failed)
        Sample.objects.create(
            individual=self.ind2, 
            sample_type=self.saliva_type, 
            status=self.failed_status, # Use sample specific status
            isolation_by=self.user,
            created_by=self.user
        )
        
        # Test, Pipeline, Analysis, Report for Ind1
        self.test_type = TestType.objects.create(name="WES", created_by=self.user)
        self.pipeline_type = PipelineType.objects.create(name="BWA", created_by=self.user)
        self.sample1 = Sample.objects.get(individual=self.ind1)
        self.test1 = LabTest.objects.create(sample=self.sample1, test_type=self.test_type, created_by=self.user)
        self.pipeline1 = Pipeline.objects.create(test=self.test1, type=self.pipeline_type, performed_date=datetime.date.today(), performed_by=self.user, created_by=self.user)
        self.analysis1 = Analysis.objects.create(pipeline=self.pipeline1, created_by=self.user)
        self.report1 = AnalysisReport.objects.create(analysis=self.analysis1, created_by=self.user)
        
        # Request Form for Ind2
        self.request_form1 = AnalysisRequestForm.objects.create(individual=self.ind2, created_by=self.user)
        
        # Project for Ind3
        self.project1 = Project.objects.create(name="Rare Diseases", created_by=self.user)
        self.project1.individuals.add(self.ind3)
        
    def test_filter_status_include(self):
        # filter status=Active
        f = IndividualFilter(data={'status': ['Active']}, queryset=Individual.objects.all())
        self.assertEqual(f.qs.count(), 2)
        self.assertIn(self.ind1, f.qs)
        self.assertIn(self.ind2, f.qs)
        
    def test_filter_status_exclude(self):
        # filter status__exclude=Active
        f = IndividualFilter(data={'status__exclude': ['Active']}, queryset=Individual.objects.all())
        self.assertEqual(f.qs.count(), 1)
        self.assertIn(self.ind3, f.qs)

    def test_filter_sex_include(self):
        f = IndividualFilter(data={'sex': ['male']}, queryset=Individual.objects.all())
        self.assertEqual(f.qs.count(), 2)
        self.assertIn(self.ind1, f.qs)
        self.assertIn(self.ind3, f.qs)

    def test_filter_sex_exclude(self):
        f = IndividualFilter(data={'sex__exclude': ['male']}, queryset=Individual.objects.all())
        self.assertEqual(f.qs.count(), 1)
        self.assertIn(self.ind2, f.qs)

    def test_filter_sample_type_include(self):
        # Individuals with Blood sample
        f = IndividualFilter(data={'samples__sample_type': ['Blood']}, queryset=Individual.objects.all())
        self.assertEqual(f.qs.count(), 1)
        self.assertIn(self.ind1, f.qs)

    def test_filter_sample_status_exclude(self):
        # Individuals WITHOUT Failed samples
        # Note: Excluding related objects can be tricky. 
        # Django's exclude(samples__status='Failed') excludes individuals who have *at least one* failed sample.
        # This means if they have a failed sample, they are gone.
        # Ind2 has a Failed sample. Ind1 has Active. Ind3 has no samples.
        f = IndividualFilter(data={'samples__status__exclude': ['Failed']}, queryset=Individual.objects.all())
        # Ind2 should be excluded.
        # Ind1 and Ind3 should remain.
        self.assertEqual(f.qs.count(), 2)
        self.assertIn(self.ind1, f.qs)
        self.assertIn(self.ind3, f.qs)

    def test_mixed_include_exclude(self):
        # Status Active AND NOT Female
        data = {
            'status': ['Active'],
            'sex__exclude': ['female']
        }
        f = IndividualFilter(data=data, queryset=Individual.objects.all())
        self.assertEqual(f.qs.count(), 1)
        self.assertIn(self.ind1, f.qs)

    def test_status_choices_restriction(self):
        # Create ContentTypes (if not already loaded, but they should be)
        from django.contrib.contenttypes.models import ContentType
        ind_ct = ContentType.objects.get_for_model(Individual)
        sample_ct = ContentType.objects.get_for_model(Sample)
        
        # Create specific statuses
        s1 = Status.objects.create(name="IndStatus", content_type=ind_ct, created_by=self.user)
        s2 = Status.objects.create(name="SampleStatus", content_type=sample_ct, created_by=self.user)
        s3 = Status.objects.create(name="GlobalStatus", content_type=None, created_by=self.user) # Should be excluded if we strictly filter by CT
        
        f = IndividualFilter(queryset=Individual.objects.all())
        
        # Check 'status' filter (Individual)
        status_qs = f.filters['status'].queryset
        self.assertIn(s1, status_qs)
        self.assertNotIn(s2, status_qs)
        # s3 might be excluded if logic is strict status.content_type = ct. 
        # My implementation was: Status.objects.filter(content_type=ct)
        self.assertNotIn(s3, status_qs)
        
        # Check 'samples__status' filter (Sample)
        sample_status_qs = f.filters['samples__status'].queryset
        self.assertNotIn(s1, sample_status_qs)
        self.assertIn(s2, sample_status_qs)

    def test_has_report_filter(self):
        f = IndividualFilter(data={'has_report': 'true'}, queryset=Individual.objects.all())
        self.assertEqual(f.qs.count(), 1)
        self.assertIn(self.ind1, f.qs)
        
        f2 = IndividualFilter(data={'has_report': 'false'}, queryset=Individual.objects.all())
        self.assertEqual(f2.qs.count(), 2)
        self.assertIn(self.ind2, f2.qs)
        self.assertIn(self.ind3, f2.qs)

    def test_has_request_form_filter(self):
        f = IndividualFilter(data={'has_request_form': 'true'}, queryset=Individual.objects.all())
        self.assertEqual(f.qs.count(), 1)
        self.assertIn(self.ind2, f.qs)
        
        f2 = IndividualFilter(data={'has_request_form': 'false'}, queryset=Individual.objects.all())
        self.assertEqual(f2.qs.count(), 2)
        self.assertIn(self.ind1, f2.qs)
        self.assertIn(self.ind3, f2.qs)

    def test_filter_projects(self):
        f = IndividualFilter(data={'projects': ['Rare Diseases']}, queryset=Individual.objects.all())
        self.assertEqual(f.qs.count(), 1)
        self.assertIn(self.ind3, f.qs)
        
        f2 = IndividualFilter(data={'projects__exclude': ['Rare Diseases']}, queryset=Individual.objects.all())
        self.assertEqual(f2.qs.count(), 2)
        self.assertIn(self.ind1, f2.qs)
        self.assertIn(self.ind2, f2.qs)

    def test_filter_is_affected(self):
        f = IndividualFilter(data={'is_affected': ['True']}, queryset=Individual.objects.all())
        self.assertEqual(f.qs.count(), 2)
        self.assertIn(self.ind1, f.qs)
        self.assertIn(self.ind3, f.qs)

        f2 = IndividualFilter(data={'is_affected': ['False']}, queryset=Individual.objects.all())
        self.assertEqual(f2.qs.count(), 1)
        self.assertIn(self.ind2, f2.qs)

    def test_filter_is_index(self):
        f = IndividualFilter(data={'is_index': ['True']}, queryset=Individual.objects.all())
        self.assertEqual(f.qs.count(), 1)
        self.assertIn(self.ind1, f.qs)

        f2 = IndividualFilter(data={'is_index': ['False']}, queryset=Individual.objects.all())
        self.assertEqual(f2.qs.count(), 2)
        self.assertIn(self.ind2, f2.qs)
        self.assertIn(self.ind3, f2.qs)
