from datetime import date
from datetime import timedelta
from calendar import monthrange

from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.test import override_settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from lab.models import (
    Analysis,
    AnalysisType,
    CrossIdentifier,
    IdentifierType,
    Individual,
    Pipeline,
    PipelineType,
    Project,
    ProjectMembership,
    Sample,
    SampleType,
    Status,
    Test as LabTest,
    TestType,
)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    MIDDLEWARE=[
        middleware
        for middleware in settings.MIDDLEWARE
        if middleware != "reversion.middleware.RevisionMiddleware"
    ],
)
class BulkAnalysisCreateModalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="bulk-analysis-user",
            password="password",
        )
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Analysis),
                codename="add_analysis",
            )
        )
        self.client.force_login(self.user)

        self.id_type = IdentifierType.objects.create(
            name="RareBoost",
            use_priority=1,
            created_by=self.user,
        )
        self.blood_type = SampleType.objects.create(name="Blood", created_by=self.user)
        self.saliva_type = SampleType.objects.create(name="Saliva", created_by=self.user)
        self.wgs_type = TestType.objects.create(name="WGS", created_by=self.user)
        self.wes_type = TestType.objects.create(name="WES", created_by=self.user)
        self.pipeline_type = PipelineType.objects.create(
            name="GATK",
            version="4.0",
            created_by=self.user,
        )
        self.other_pipeline_type = PipelineType.objects.create(
            name="Dragen",
            version="1.2",
            created_by=self.user,
        )
        self.analysis_type = AnalysisType.objects.create(
            name="Initial Analysis",
            created_by=self.user,
        )
        self.default_status = Status.objects.create(
            name="Planned",
            content_type=ContentType.objects.get_for_model(Analysis),
            created_by=self.user,
        )

        self.first = Individual.objects.create(full_name="First Individual", created_by=self.user)
        self.second = Individual.objects.create(full_name="Second Individual", created_by=self.user)
        self.no_pipeline = Individual.objects.create(
            full_name="No Pipeline Individual",
            created_by=self.user,
        )
        self.project = Project.objects.create(name="Bulk Analysis Project", created_by=self.user)
        self.project.individuals.add(self.first, self.second, self.no_pipeline)
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ProjectMembership.Role.EDITOR,
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.first,
            id_type=self.id_type,
            id_value="RB_2026_301.1",
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.second,
            id_type=self.id_type,
            id_value="RB_2026_302.1",
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.no_pipeline,
            id_type=self.id_type,
            id_value="RB_2026_303.1",
            created_by=self.user,
        )

        self.first_sample = Sample.objects.create(
            individual=self.first,
            sample_type=self.blood_type,
            receipt_date=date(2026, 1, 15),
            created_by=self.user,
        )
        self.first_second_sample = Sample.objects.create(
            individual=self.first,
            sample_type=self.saliva_type,
            created_by=self.user,
        )
        self.second_sample = Sample.objects.create(
            individual=self.second,
            sample_type=self.saliva_type,
            created_by=self.user,
        )
        self.no_pipeline_sample = Sample.objects.create(
            individual=self.no_pipeline,
            sample_type=self.blood_type,
            created_by=self.user,
        )
        self.first_test = LabTest.objects.create(
            sample=self.first_sample,
            test_type=self.wgs_type,
            created_by=self.user,
        )
        self.first_second_test = LabTest.objects.create(
            sample=self.first_second_sample,
            test_type=self.wes_type,
            created_by=self.user,
        )
        self.second_test = LabTest.objects.create(
            sample=self.second_sample,
            test_type=self.wgs_type,
            created_by=self.user,
        )
        self.no_pipeline_test = LabTest.objects.create(
            sample=self.no_pipeline_sample,
            test_type=self.wgs_type,
            created_by=self.user,
        )
        self.first_pipeline = Pipeline.objects.create(
            test=self.first_test,
            type=self.pipeline_type,
            performed_date=date(2026, 8, 20),
            performed_by=self.user,
            created_by=self.user,
        )
        self.first_second_pipeline = Pipeline.objects.create(
            test=self.first_second_test,
            type=self.other_pipeline_type,
            performed_date=date(2026, 8, 21),
            performed_by=self.user,
            created_by=self.user,
        )
        self.second_pipeline = Pipeline.objects.create(
            test=self.second_test,
            type=self.pipeline_type,
            performed_date=date(2026, 8, 22),
            performed_by=self.user,
            created_by=self.user,
        )

    def test_bulk_create_dropdown_renders_analysis_modal_url(self):
        html = render_to_string("lab/components/bulk_create_dropdown.html")

        self.assertIn(reverse("lab:bulk_analysis_create_modal"), html)
        self.assertIn('data-bulk-create-type="analysis"', html)
        self.assertIn("Analyses", html)

    def test_bulk_analysis_create_modal_renders_lookup_form(self):
        response = self.client.get(
            reverse("lab:bulk_analysis_create_modal"),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bulk Create Analyses")
        self.assertContains(response, "Find Individuals")

    def test_bulk_analysis_create_modal_returns_matching_individual_ids(self):
        response = self.client.post(
            reverse("lab:bulk_analysis_create_modal"),
            {"ids": "RB_2026_301.1, missing-id\nRB_2026_302.1"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bulk Create Analyses")
        self.assertContains(response, "Add Analyses")
        self.assertContains(response, str(self.first.pk))
        self.assertContains(response, "RB_2026_301.1")
        self.assertContains(response, str(self.second.pk))
        self.assertContains(response, "RB_2026_302.1")
        self.assertContains(response, f'name="individual_ids" value="{self.first.pk}"')
        self.assertContains(response, f'name="individual_ids" value="{self.second.pk}"')
        self.assertNotContains(response, "Object ID")

    def test_add_analyses_button_renders_bulk_analysis_rows(self):
        response = self.client.post(
            reverse("lab:bulk_analysis_create_form"),
            {"individual_ids": [str(self.first.pk), str(self.second.pk)]},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Analyses")
        self.assertContains(response, "Sample")
        self.assertContains(response, "Test")
        self.assertContains(response, "Pipeline")
        self.assertContains(response, "Analysis Type")
        self.assertContains(response, "Performed Date")
        self.assertContains(response, "Performed By")
        self.assertContains(response, "analyses-0-sample")
        self.assertContains(response, "analyses-0-test")
        self.assertContains(response, "analyses-0-pipeline")
        self.assertContains(response, "analyses-0-analysis_type")
        self.assertContains(response, "analyses-0-performed_date")
        self.assertContains(response, "analyses-0-performed_by")
        self.assertNotContains(response, "Object ID")

    def test_bulk_analysis_rows_only_show_samples_from_each_individual(self):
        response = self.client.post(
            reverse("lab:bulk_analysis_create_form"),
            {"individual_ids": [str(self.first.pk), str(self.second.pk)]},
            HTTP_HX_REQUEST="true",
        )

        html = response.content.decode()
        first_select = html.split('id="id_analyses-0-sample"', 1)[1].split(
            "</select>", 1
        )[0]
        second_select = html.split('id="id_analyses-1-sample"', 1)[1].split(
            "</select>", 1
        )[0]

        self.assertIn(f"value=\"{self.first_sample.pk}\"", first_select)
        self.assertIn(f"value=\"{self.first_second_sample.pk}\"", first_select)
        self.assertNotIn(f"value=\"{self.second_sample.pk}\"", first_select)
        self.assertIn(f"value=\"{self.second_sample.pk}\"", second_select)
        self.assertNotIn(f"value=\"{self.first_sample.pk}\"", second_select)

    def test_analysis_test_options_update_from_selected_sample_and_reset_pipeline(self):
        response = self.client.get(
            reverse("lab:bulk_analysis_test_options"),
            {
                "analyses-0-sample": str(self.first_second_sample.pk),
                "field_name": "analyses-0-test",
                "field_id": "id_analyses-0-test",
                "pipeline_field_name": "analyses-0-pipeline",
                "pipeline_field_id": "id_analyses-0-pipeline",
                "pipeline_cell_id": "pipeline-options-analyses-0",
                "individual_id": str(self.first.pk),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="analyses-0-test"')
        self.assertContains(response, 'id="id_analyses-0-test"')
        self.assertContains(response, f"value=\"{self.first_second_test.pk}\"")
        self.assertContains(response, "WES")
        self.assertContains(response, 'id="pipeline-options-analyses-0"')
        self.assertContains(response, 'hx-swap-oob="innerHTML"')
        self.assertNotContains(response, f"value=\"{self.first_test.pk}\"")
        self.assertNotContains(response, f"value=\"{self.second_test.pk}\"")

    def test_analysis_pipeline_options_update_from_selected_test(self):
        response = self.client.get(
            reverse("lab:bulk_analysis_pipeline_options"),
            {
                "analyses-0-test": str(self.first_test.pk),
                "field_name": "analyses-0-pipeline",
                "field_id": "id_analyses-0-pipeline",
                "sample_id": str(self.first_sample.pk),
                "individual_id": str(self.first.pk),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="analyses-0-pipeline"')
        self.assertContains(response, 'id="id_analyses-0-pipeline"')
        self.assertContains(response, f"value=\"{self.first_pipeline.pk}\"")
        self.assertContains(response, "GATK")
        self.assertNotContains(response, f"value=\"{self.first_second_pipeline.pk}\"")
        self.assertNotContains(response, f"value=\"{self.second_pipeline.pk}\"")

    def test_analysis_pipeline_options_reject_wrong_sample_scope(self):
        response = self.client.get(
            reverse("lab:bulk_analysis_pipeline_options"),
            {
                "analyses-0-test": str(self.first_test.pk),
                "field_name": "analyses-0-pipeline",
                "field_id": "id_analyses-0-pipeline",
                "sample_id": str(self.second_sample.pk),
                "individual_id": str(self.second.pk),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Selected test has no pipelines.")
        self.assertNotContains(response, f"value=\"{self.first_pipeline.pk}\"")

    def test_bulk_analysis_rows_warn_when_an_individual_has_no_pipelines(self):
        response = self.client.post(
            reverse("lab:bulk_analysis_create_form"),
            {"individual_ids": [str(self.no_pipeline.pk)]},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This individual's tests have no pipelines.")
        self.assertContains(response, "Create Analyses")
        self.assertContains(response, "disabled")

    def test_bulk_analysis_rows_render_performed_date_shortcuts(self):
        response = self.client.post(
            reverse("lab:bulk_analysis_create_form"),
            {"individual_ids": [str(self.second.pk)]},
            HTTP_HX_REQUEST="true",
        )

        today = timezone.localdate()
        previous_month = 12 if today.month == 1 else today.month - 1
        previous_month_year = today.year - 1 if today.month == 1 else today.year
        last_month = today.replace(
            year=previous_month_year,
            month=previous_month,
            day=min(today.day, monthrange(previous_month_year, previous_month)[1]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tdy")
        self.assertContains(response, "Ystrdy")
        self.assertContains(response, "LW")
        self.assertContains(response, "LM")
        self.assertContains(response, f'data-performed-date-value="{today.isoformat()}"')
        self.assertContains(
            response,
            f'data-performed-date-value="{(today - timedelta(days=1)).isoformat()}"',
        )
        self.assertContains(
            response,
            f'data-performed-date-value="{(today - timedelta(days=7)).isoformat()}"',
        )
        self.assertContains(
            response,
            f'data-performed-date-value="{last_month.isoformat()}"',
        )

    def test_bulk_analysis_rows_create_analyses_with_required_fields(self):
        response = self.client.post(
            reverse("lab:bulk_analysis_create_form"),
            {
                "bulk_analysis_action": "create",
                "analyses-TOTAL_FORMS": "2",
                "analyses-INITIAL_FORMS": "0",
                "analyses-MIN_NUM_FORMS": "1",
                "analyses-MAX_NUM_FORMS": "1000",
                "analyses-0-individual": str(self.first.pk),
                "analyses-0-sample": str(self.first_sample.pk),
                "analyses-0-test": str(self.first_test.pk),
                "analyses-0-pipeline": str(self.first_pipeline.pk),
                "analyses-0-analysis_type": str(self.analysis_type.pk),
                "analyses-0-performed_date": "2026-08-31",
                "analyses-0-performed_by": [str(self.user.pk)],
                "analyses-1-individual": str(self.second.pk),
                "analyses-1-sample": str(self.second_sample.pk),
                "analyses-1-test": str(self.second_test.pk),
                "analyses-1-pipeline": str(self.second_pipeline.pk),
                "analyses-1-analysis_type": str(self.analysis_type.pk),
                "analyses-1-performed_date": "2026-08-31",
                "analyses-1-performed_by": [str(self.user.pk)],
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 analyses created")

        analyses = Analysis.objects.select_related(
            "pipeline",
            "type",
            "created_by",
        ).order_by("pipeline_id")
        self.assertEqual(analyses.count(), 2)
        self.assertEqual(analyses[0].pipeline, self.first_pipeline)
        self.assertEqual(analyses[0].type, self.analysis_type)
        self.assertEqual(analyses[0].performed_date, date(2026, 8, 31))
        self.assertEqual(list(analyses[0].performed_by.all()), [self.user])
        self.assertEqual(analyses[0].created_by, self.user)
        self.assertTrue(analyses[0].statuses.filter(pk=self.default_status.pk).exists())
        self.assertEqual(analyses[1].pipeline, self.second_pipeline)

    def test_bulk_analysis_rows_reject_pipeline_from_different_test(self):
        response = self.client.post(
            reverse("lab:bulk_analysis_create_form"),
            {
                "bulk_analysis_action": "create",
                "analyses-TOTAL_FORMS": "1",
                "analyses-INITIAL_FORMS": "0",
                "analyses-MIN_NUM_FORMS": "1",
                "analyses-MAX_NUM_FORMS": "1000",
                "analyses-0-individual": str(self.first.pk),
                "analyses-0-sample": str(self.first_sample.pk),
                "analyses-0-test": str(self.first_test.pk),
                "analyses-0-pipeline": str(self.first_second_pipeline.pk),
                "analyses-0-analysis_type": str(self.analysis_type.pk),
                "analyses-0-performed_date": "2026-08-31",
                "analyses-0-performed_by": [str(self.user.pk)],
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertEqual(Analysis.objects.count(), 0)

    def test_bulk_analysis_rows_do_not_create_partial_analyses(self):
        response = self.client.post(
            reverse("lab:bulk_analysis_create_form"),
            {
                "bulk_analysis_action": "create",
                "analyses-TOTAL_FORMS": "2",
                "analyses-INITIAL_FORMS": "0",
                "analyses-MIN_NUM_FORMS": "1",
                "analyses-MAX_NUM_FORMS": "1000",
                "analyses-0-individual": str(self.first.pk),
                "analyses-0-sample": str(self.first_sample.pk),
                "analyses-0-test": str(self.first_test.pk),
                "analyses-0-pipeline": str(self.first_pipeline.pk),
                "analyses-0-analysis_type": str(self.analysis_type.pk),
                "analyses-0-performed_date": "2026-08-31",
                "analyses-0-performed_by": [str(self.user.pk)],
                "analyses-1-individual": str(self.second.pk),
                "analyses-1-sample": str(self.second_sample.pk),
                "analyses-1-test": str(self.second_test.pk),
                "analyses-1-pipeline": str(self.second_pipeline.pk),
                "analyses-1-analysis_type": "",
                "analyses-1-performed_date": "2026-08-31",
                "analyses-1-performed_by": [str(self.user.pk)],
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose an analysis type.")
        self.assertEqual(Analysis.objects.count(), 0)

    def test_bulk_analysis_endpoints_require_add_analysis_permission(self):
        self.user.user_permissions.clear()

        endpoints = [
            ("get", reverse("lab:bulk_analysis_create_modal")),
            ("post", reverse("lab:bulk_analysis_create_form")),
            ("get", reverse("lab:bulk_analysis_test_options")),
            ("get", reverse("lab:bulk_analysis_pipeline_options")),
        ]
        for method, url in endpoints:
            response = getattr(self.client, method)(url)
            self.assertEqual(response.status_code, 403)
