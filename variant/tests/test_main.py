from django.test import TestCase
from django.contrib.auth.models import User
from lab.models import Individual, Analysis, Status, Test, TestType, Sample, SampleType, AnalysisType
from variant.models import SNV, Variant, Annotation, Classification
from variant.services import DiagnosticService, AnnotationService

class VariantModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="testuser")
        self.status = Status.objects.create(name="Active", created_by=self.user)
        self.individual = Individual.objects.create(
            full_name="Test Indiv", created_by=self.user, status=self.status
        )

    def test_snv_creation(self):
        snv = SNV.objects.create(
            chromosome="1", start=100, end=100, reference="A", alternate="T",
            individual=self.individual, created_by=self.user
        )
        self.assertEqual(Variant.objects.count(), 1)
        self.assertEqual(snv.chromosome, "chr1")
        self.assertEqual(str(snv), "chr1:100 A>T")

    def test_classification_creation(self):
        snv = SNV.objects.create(
            chromosome="1", start=100, end=100, reference="A", alternate="T",
            individual=self.individual, created_by=self.user
        )
        classification = Classification.objects.create(
            variant=snv, user=self.user, classification="pathogenic", inheritance="ad"
        )
        self.assertEqual(classification.classification, "pathogenic")
        self.assertEqual(snv.classifications.count(), 1)

class ServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="testuser")
        self.status_solved = Status.objects.create(name="Solved - P/LP", created_by=self.user)
        self.status_neg = Status.objects.create(name="Negative", created_by=self.user)
        self.individual = Individual.objects.create(
            full_name="Test Indiv", created_by=self.user, status=self.status_neg
        )
        self.sample_type = SampleType.objects.create(name="Blood", created_by=self.user)
        self.sample = Sample.objects.create(
            individual=self.individual, sample_type=self.sample_type, 
            status=self.status_neg, created_by=self.user,
            isolation_by=self.user
        )
        self.test_type = TestType.objects.create(name="WGS", created_by=self.user)
        self.test = Test.objects.create(
            sample=self.sample, test_type=self.test_type, 
            status=self.status_neg, created_by=self.user
        )
        self.analysis_type = AnalysisType.objects.create(name="WGS Analysis", created_by=self.user)

    def test_diagnostic_yield(self):
        # Create 1 solved, 1 negative
        Analysis.objects.create(
            test=self.test, type=self.analysis_type, status=self.status_solved, 
            performed_date="2023-01-01", performed_by=self.user, created_by=self.user
        )
        Analysis.objects.create(
            test=self.test, type=self.analysis_type, status=self.status_neg, 
            performed_date="2023-01-01", performed_by=self.user, created_by=self.user
        )
        
        ds = DiagnosticService()
        result = ds.get_diagnostic_yield()
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['solved'], 1)
        self.assertEqual(result['yield_percentage'], 50.0)

    def test_annotation_service_mock(self):
        # We won't call real APIs in tests, just check method existence
        service = AnnotationService()
        self.assertTrue(hasattr(service, 'fetch_myvariant_info'))

class VariantViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.client.login(username="testuser", password="password")
        self.status = Status.objects.create(name="Active", created_by=self.user)
        self.individual = Individual.objects.create(
            full_name="Test Indiv", created_by=self.user, status=self.status
        )
        self.sample_type = SampleType.objects.create(name="Blood", created_by=self.user)
        self.sample = Sample.objects.create(
            individual=self.individual, sample_type=self.sample_type, 
            status=self.status, created_by=self.user,
            isolation_by=self.user
        )
        self.test_type = TestType.objects.create(name="WGS", created_by=self.user)
        self.test = Test.objects.create(
            sample=self.sample, test_type=self.test_type, 
            status=self.status, created_by=self.user
        )
        self.analysis_type = AnalysisType.objects.create(name="WGS Analysis", created_by=self.user)
        self.analysis = Analysis.objects.create(
            test=self.test, type=self.analysis_type, status=self.status, 
            performed_date="2023-01-01", performed_by=self.user, created_by=self.user
        )

    def test_variant_create_view_get(self):
        response = self.client.get(
            "/variant/create/", 
            {"analysis_id": self.analysis.id, "type": "snv"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "variant/variant_form.html")

    def test_variant_create_view_post_snv(self):
        data = {
            "assembly_version": "hg38",
            "chromosome": "1",
            "start": 100,
            "end": 100,
            "reference": "A",
            "alternate": "T"
        }
        response = self.client.post(
            f"/variant/create/?analysis_id={self.analysis.id}&type=snv",
            data
        )
        self.assertEqual(response.status_code, 302) # Redirect
        self.assertEqual(SNV.objects.count(), 1)
        snv = SNV.objects.first()
        self.assertEqual(snv.analysis, self.analysis)
        self.assertEqual(snv.individual, self.individual)

    def test_variant_create_view_post_htmx(self):
        data = {
            "assembly_version": "hg38",
            "chromosome": "2",
            "start": 200,
            "end": 200,
            "reference": "G",
            "alternate": "C"
        }
        response = self.client.post(
            f"/variant/create/?analysis_id={self.analysis.id}&type=snv",
            data,
            headers={"HX-Request": "true"}
        )
        self.assertEqual(response.status_code, 200)
        # assertTemplateUsed might be flaky with partials or if render is called directly with fragment
        # So we check content
        self.assertIn(b"chr2:200G&gt;C", response.content)
        self.assertIn("HX-Trigger", response)
        self.assertEqual(SNV.objects.count(), 1)
