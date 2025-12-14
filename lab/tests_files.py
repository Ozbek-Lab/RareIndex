from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from lab.models import Individual, AnalysisRequestForm
from variant.models import AnalysisReport, Variant, Analysis
from lab.models import Test, Sample, TestType, SampleType, Status, AnalysisType

User = get_user_model()

class AnalysisFilesTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.status = Status.objects.create(name='Active', created_by=self.user)
        self.individual = Individual.objects.create(
            full_name='Test Individual',
            created_by=self.user,
            status=self.status
        )
        self.sample_type = SampleType.objects.create(name='Blood', created_by=self.user)
        self.sample = Sample.objects.create(
            individual=self.individual,
            sample_type=self.sample_type,
            status=self.status,
            isolation_by=self.user,
            created_by=self.user
        )
        self.test_type = TestType.objects.create(name='WGS', created_by=self.user)
        self.test = Test.objects.create(
            sample=self.sample,
            test_type=self.test_type,
            status=self.status,
            created_by=self.user
        )
        self.analysis_type = AnalysisType.objects.create(name='Routine', created_by=self.user)
        self.analysis = Analysis.objects.create(
            test=self.test,
            type=self.analysis_type,
            status=self.status,
            performed_date='2024-01-01',
            performed_by=self.user,
            created_by=self.user
        )
        self.variant = Variant.objects.create(
            chromosome='chr1',
            start=100,
            end=200,
            individual=self.individual,
            created_by=self.user
        )

    def test_analysis_request_form(self):
        file = SimpleUploadedFile("request.docx", b"dummy content")
        form = AnalysisRequestForm.objects.create(
            individual=self.individual,
            file=file,
            created_by=self.user
        )
        self.assertEqual(form.individual, self.individual)
        self.assertTrue(form.file.name.startswith('analysis_requests/'), f"Got {form.file.name}")
        self.assertTrue(form.file.name.endswith('.docx'), f"Got {form.file.name}")

    def test_analysis_report(self):
        file = SimpleUploadedFile("report.pdf", b"dummy content")
        report = AnalysisReport.objects.create(
            analysis=self.analysis,
            file=file,
            created_by=self.user
        )
        report.variants.add(self.variant)
        
        self.assertEqual(report.analysis, self.analysis)
        self.assertIn(self.variant, report.variants.all())
        self.assertTrue(report.file.name.startswith('analysis_reports/'), f"Got {report.file.name}")
        self.assertTrue(report.file.name.endswith('.pdf'), f"Got {report.file.name}")

    def test_analysis_report_form_filtering(self):
        from lab.forms import AnalysisReportForm
        
        # Link variant to analysis via found_variants
        # Note: Variant has 'analysis' FK for this purpose
        self.variant.analysis = self.analysis
        self.variant.save()
        
        # Create another variant not linked to this analysis
        other_variant = Variant.objects.create(
            chromosome='chr2',
            start=100,
            end=200,
            individual=self.individual,
            created_by=self.user
        )
        
        # Initialize form with initial data
        form = AnalysisReportForm(initial={'analysis': self.analysis.pk})
        
        # Verify queryset
        qs = form.fields['variants'].queryset
        self.assertIn(self.variant, qs)
        self.assertNotIn(other_variant, qs)
        
        # Test with bound data (POST simulation)
        form_bound = AnalysisReportForm(data={'analysis': self.analysis.pk})
        qs_bound = form_bound.fields['variants'].queryset
        self.assertIn(self.variant, qs_bound)
        self.assertNotIn(other_variant, qs_bound)

    def test_filter_has_request_form(self):
        from lab.filters import apply_filters
        
        # Create a second individual without a form
        indiv2 = Individual.objects.create(
            full_name='No Form Individual',
            created_by=self.user,
            status=self.status
        )
        
        # Create form for self.individual
        file = SimpleUploadedFile("request.docx", b"dummy content")
        AnalysisRequestForm.objects.create(
            individual=self.individual,
            file=file,
            created_by=self.user
        )
        
        qs = Individual.objects.all()
        
        # Filter for has_request_form=true
        request = self.client.get('/', {'filter_has_request_form': 'true'}).wsgi_request
        filtered_qs = apply_filters(request, 'Individual', qs)
        
        self.assertIn(self.individual, filtered_qs)
        self.assertNotIn(indiv2, filtered_qs)
        
        # Filter for has_request_form=false (should show indiv2, maybe self.individual if logic allows? Usually existence filter is just yes/no)
        # My implementation handles 'false' as isnull=True (doesn't have form)
        request = self.client.get('/', {'filter_has_request_form': 'false'}).wsgi_request
        filtered_qs = apply_filters(request, 'Individual', qs)
        
        self.assertIn(indiv2, filtered_qs)
        self.assertNotIn(self.individual, filtered_qs)

    def test_filter_has_analysis_report(self):
        from lab.filters import apply_filters
        
        # Create a second individual without a report
        indiv2 = Individual.objects.create(
            full_name='No Report Individual',
            created_by=self.user,
            status=self.status
        )
        
        # Create report for self.individual (via self.analysis -> self.test -> self.sample -> self.individual)
        file = SimpleUploadedFile("report.pdf", b"dummy content")
        AnalysisReport.objects.create(
            analysis=self.analysis,
            file=file,
            created_by=self.user
        )
        
        qs = Individual.objects.all()
        
        # Filter for has_analysis_report=true
        request = self.client.get('/', {'filter_has_analysis_report': 'true'}).wsgi_request
        filtered_qs = apply_filters(request, 'Individual', qs)
        
        self.assertIn(self.individual, filtered_qs)
        self.assertNotIn(indiv2, filtered_qs)
        
        # Filter for has_analysis_report=false
        request = self.client.get('/', {'filter_has_analysis_report': 'false'}).wsgi_request
        filtered_qs = apply_filters(request, 'Individual', qs)
        
        self.assertIn(indiv2, filtered_qs)
        self.assertNotIn(self.individual, filtered_qs)
