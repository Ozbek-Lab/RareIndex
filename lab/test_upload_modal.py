from datetime import date
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from lab.htmx_views import report_replace_modal, request_form_create_modal
from lab.models import (
    Analysis, AnalysisReport, AnalysisRequestForm, Individual, Pipeline,
    PipelineType, Sample, SampleType, Test as LabTest, TestType,
)


class UploadModalTargetTests(SimpleTestCase):
    def test_optional_targets_resolve_without_missing_variable_errors(self):
        for context, expected in [
            ({"hx_target": "#request-forms-card-608 .card-body"}, "#request-forms-card-608 .card-body"),
            ({"workflow_target_id": "#workflow-content-608"}, "#workflow-content-608"),
            ({"hx_target": "#request-forms", "workflow_target_id": "#workflow"}, "#request-forms"),
            ({"hx_target": "", "workflow_target_id": "#workflow"}, "#workflow"),
            ({}, "#workflow-content"),
        ]:
            with self.subTest(context=context):
                html = render_to_string("lab/partials/modals/upload_modal_form.html", context)
                self.assertIn(f'hx-target="{expected}"', html)


class RequestFormUploadModalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(username="request-form-uploader")
        cls.individual = Individual.objects.create(created_by=cls.user)

    def setUp(self):
        self.factory = RequestFactory()
        self.url = reverse("lab:request_form_create_modal", args=[self.individual.pk])

    def request(self, method, data=None):
        request = getattr(self.factory, method)(self.url, data or {}, HTTP_HX_REQUEST="true")
        request.user = self.user
        return request_form_create_modal(request, self.individual.pk)

    def test_open_upload_modal_targets_request_form_card(self):
        response = self.request("get")
        self.assertContains(response, f'hx-target="#request-forms-card-{self.individual.pk} .card-body"')
        self.assertContains(response, f'hx-post="{self.url}"')
        self.assertContains(response, 'hx-encoding="multipart/form-data"')

    def test_missing_file_renders_validation_errors_without_server_error(self):
        response = self.request("post", {"description": "Missing file"})
        self.assertContains(response, "This field is required.")
        self.assertContains(response, f'hx-target="#request-forms-card-{self.individual.pk} .card-body"')
        self.assertFalse(AnalysisRequestForm.objects.exists())

    def test_upload_saves_file_and_returns_updated_card(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            upload = SimpleUploadedFile("request.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf")
            response = self.request("post", {"file": upload, "description": "Test request"})
            self.assertContains(response, "request.pdf")
            uploaded = AnalysisRequestForm.objects.get()
            self.assertEqual(uploaded.individual, self.individual)
            self.assertEqual(uploaded.created_by, self.user)
            self.assertEqual(uploaded.description, "Test request")
            with uploaded.file.open("rb") as saved:
                self.assertEqual(saved.read(), b"%PDF-1.4\n%%EOF")


class ReportReplacementModalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(username="report-replacer")
        cls.individual = Individual.objects.create(created_by=cls.user)
        sample_type = SampleType.objects.create(name="Blood", created_by=cls.user)
        sample = Sample.objects.create(individual=cls.individual, sample_type=sample_type, created_by=cls.user)
        test_type = TestType.objects.create(name="WES", created_by=cls.user)
        test = LabTest.objects.create(sample=sample, test_type=test_type, created_by=cls.user)
        pipeline_type = PipelineType.objects.create(name="Analysis pipeline", created_by=cls.user)
        pipeline = Pipeline.objects.create(
            test=test, type=pipeline_type, performed_date=date(2026, 1, 1),
            performed_by=cls.user, created_by=cls.user,
        )
        cls.analysis = Analysis.objects.create(pipeline=pipeline, created_by=cls.user)

    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=directory))
        self.report = AnalysisReport.objects.create(
            analysis=self.analysis, created_by=self.user,
            file=SimpleUploadedFile("original.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        )
        self.factory = RequestFactory()
        self.url = reverse("lab:report_replace_modal", args=[self.report.pk])
        self.target = f"#workflow-content-{self.individual.pk}"

    def request(self, method, data=None):
        request = getattr(self.factory, method)(self.url, data or {}, HTTP_HX_REQUEST="true")
        request.user = self.user
        return report_replace_modal(request, self.report.pk)

    def test_open_replace_modal_targets_individual_workflow(self):
        response = self.request("get")
        self.assertContains(response, "Replace Analysis Report File")
        self.assertContains(response, f'hx-target="{self.target}"')
        self.assertContains(response, f'hx-post="{self.url}"')

    def test_missing_replacement_file_renders_errors(self):
        original_name = self.report.file.name
        response = self.request("post", {"action": "replace"})
        self.assertContains(response, "This field is required.")
        self.assertContains(response, f'hx-target="{self.target}"')
        self.report.refresh_from_db()
        self.assertEqual(self.report.file.name, original_name)

    def test_replacement_saves_file_and_refreshes_workflow(self):
        content = b"%PDF-1.4\n% replacement\n%%EOF"
        upload = SimpleUploadedFile("replacement.pdf", content, content_type="application/pdf")
        response = self.request("post", {"file": upload})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Retarget"], self.target)
        self.assertContains(response, "replacement.pdf")
        self.report.refresh_from_db()
        with self.report.file.open("rb") as saved:
            self.assertEqual(saved.read(), content)

    def test_delete_still_refreshes_workflow(self):
        storage = self.report.file.storage
        filename = self.report.file.name
        response = self.request("post", {"action": "delete"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Retarget"], self.target)
        self.assertFalse(AnalysisReport.objects.filter(pk=self.report.pk).exists())
        self.assertFalse(storage.exists(filename))

    def test_report_without_analysis_uses_default_workflow_target(self):
        self.report.analysis = None
        self.report.save(update_fields=["analysis"])
        response = self.request("get")
        self.assertContains(response, 'hx-target="#workflow-content"')
