from django.test import TestCase
from lab.models import Individual, Status, Sample, SampleType
from lab.filters import IndividualFilter
from django.contrib.auth.models import User

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
            status=self.active_status,
            created_by=self.user
        )
        self.ind2 = Individual.objects.create(
            full_name="Jane Doe", 
            sex="female", 
            status=self.active_status,
            created_by=self.user
        )
        self.ind3 = Individual.objects.create(
            full_name="Inactive User", 
            sex="male", 
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
