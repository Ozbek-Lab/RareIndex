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
class BulkPipelineCreateModalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="bulk-pipeline-user",
            password="password",
        )
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Pipeline),
                codename="add_pipeline",
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
        self.default_status = Status.objects.create(
            name="Planned",
            content_type=ContentType.objects.get_for_model(Pipeline),
            created_by=self.user,
        )

        self.first = Individual.objects.create(full_name="First Individual", created_by=self.user)
        self.second = Individual.objects.create(full_name="Second Individual", created_by=self.user)
        self.no_test = Individual.objects.create(
            full_name="No Test Individual",
            created_by=self.user,
        )
        self.project = Project.objects.create(name="Bulk Pipeline Project", created_by=self.user)
        self.project.individuals.add(self.first, self.second, self.no_test)
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ProjectMembership.Role.EDITOR,
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.first,
            id_type=self.id_type,
            id_value="RB_2026_201.1",
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.second,
            id_type=self.id_type,
            id_value="RB_2026_202.1",
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.no_test,
            id_type=self.id_type,
            id_value="RB_2026_203.1",
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
        self.no_test_sample = Sample.objects.create(
            individual=self.no_test,
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

    def test_bulk_create_dropdown_renders_pipeline_modal_url(self):
        html = render_to_string("lab/components/bulk_create_dropdown.html")

        self.assertIn(reverse("lab:bulk_pipeline_create_modal"), html)

    def test_bulk_pipeline_create_modal_returns_matching_individual_ids(self):
        response = self.client.post(
            reverse("lab:bulk_pipeline_create_modal"),
            {"ids": "RB_2026_201.1, missing-id\nRB_2026_202.1"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bulk Create Pipelines")
        self.assertContains(response, "Add Pipelines")
        self.assertContains(response, str(self.first.pk))
        self.assertContains(response, "RB_2026_201.1")
        self.assertContains(response, str(self.second.pk))
        self.assertContains(response, "RB_2026_202.1")
        self.assertContains(response, f'name="individual_ids" value="{self.first.pk}"')
        self.assertContains(response, f'name="individual_ids" value="{self.second.pk}"')
        self.assertNotContains(response, "Object ID")

    def test_add_pipelines_button_renders_bulk_pipeline_rows(self):
        response = self.client.post(
            reverse("lab:bulk_pipeline_create_form"),
            {"individual_ids": [str(self.first.pk), str(self.second.pk)]},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Pipelines")
        self.assertContains(response, "Sample")
        self.assertContains(response, "Test")
        self.assertContains(response, "Pipeline Type")
        self.assertContains(response, "Performed Date")
        self.assertContains(response, "Performed By")
        self.assertContains(response, "pipelines-0-sample")
        self.assertContains(response, "pipelines-0-test")
        self.assertContains(response, "pipelines-0-pipeline_type")
        self.assertContains(response, "pipelines-1-sample")
        self.assertContains(response, "pipelines-1-test")
        self.assertNotContains(response, "Object ID")

    def test_bulk_pipeline_rows_only_show_samples_from_each_individual(self):
        response = self.client.post(
            reverse("lab:bulk_pipeline_create_form"),
            {"individual_ids": [str(self.first.pk), str(self.second.pk)]},
            HTTP_HX_REQUEST="true",
        )

        html = response.content.decode()
        first_select = html.split('id="id_pipelines-0-sample"', 1)[1].split(
            "</select>", 1
        )[0]
        second_select = html.split('id="id_pipelines-1-sample"', 1)[1].split(
            "</select>", 1
        )[0]

        self.assertIn(f"value=\"{self.first_sample.pk}\"", first_select)
        self.assertIn(f"value=\"{self.first_second_sample.pk}\"", first_select)
        self.assertNotIn(f"value=\"{self.second_sample.pk}\"", first_select)
        self.assertIn(f"value=\"{self.second_sample.pk}\"", second_select)
        self.assertNotIn(f"value=\"{self.first_sample.pk}\"", second_select)

    def test_pipeline_test_options_update_from_selected_sample(self):
        response = self.client.get(
            reverse("lab:bulk_pipeline_test_options"),
            {
                "pipelines-0-sample": str(self.first_second_sample.pk),
                "field_name": "pipelines-0-test",
                "field_id": "id_pipelines-0-test",
                "individual_id": str(self.first.pk),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="pipelines-0-test"')
        self.assertContains(response, 'id="id_pipelines-0-test"')
        self.assertContains(response, f"value=\"{self.first_second_test.pk}\"")
        self.assertContains(response, "WES")
        self.assertNotContains(response, f"value=\"{self.first_test.pk}\"")
        self.assertNotContains(response, f"value=\"{self.second_test.pk}\"")

    def test_pipeline_test_options_reject_wrong_individual_scope(self):
        response = self.client.get(
            reverse("lab:bulk_pipeline_test_options"),
            {
                "pipelines-0-sample": str(self.first_sample.pk),
                "field_name": "pipelines-0-test",
                "field_id": "id_pipelines-0-test",
                "individual_id": str(self.second.pk),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Selected sample has no tests.")
        self.assertNotContains(response, f"value=\"{self.first_test.pk}\"")

    def test_bulk_pipeline_rows_warn_when_an_individual_has_no_tests(self):
        response = self.client.post(
            reverse("lab:bulk_pipeline_create_form"),
            {"individual_ids": [str(self.no_test.pk)]},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This individual's samples have no tests.")
        self.assertContains(response, "Create Pipelines")
        self.assertContains(response, "disabled")

    def test_bulk_pipeline_rows_render_performed_date_shortcuts(self):
        response = self.client.post(
            reverse("lab:bulk_pipeline_create_form"),
            {"individual_ids": [str(self.first.pk)]},
            HTTP_HX_REQUEST="true",
        )

        today = timezone.localdate()

        self.assertEqual(response.status_code, 200)
        previous_month = 12 if today.month == 1 else today.month - 1
        previous_month_year = today.year - 1 if today.month == 1 else today.year
        last_month = today.replace(
            year=previous_month_year,
            month=previous_month,
            day=min(today.day, monthrange(previous_month_year, previous_month)[1]),
        )

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

    def test_bulk_pipeline_rows_create_pipelines_with_required_fields(self):
        response = self.client.post(
            reverse("lab:bulk_pipeline_create_form"),
            {
                "bulk_pipeline_action": "create",
                "pipelines-TOTAL_FORMS": "2",
                "pipelines-INITIAL_FORMS": "0",
                "pipelines-MIN_NUM_FORMS": "1",
                "pipelines-MAX_NUM_FORMS": "1000",
                "pipelines-0-individual": str(self.first.pk),
                "pipelines-0-sample": str(self.first_sample.pk),
                "pipelines-0-test": str(self.first_test.pk),
                "pipelines-0-pipeline_type": str(self.pipeline_type.pk),
                "pipelines-0-performed_date": "2026-08-31",
                "pipelines-0-performed_by": str(self.user.pk),
                "pipelines-1-individual": str(self.second.pk),
                "pipelines-1-sample": str(self.second_sample.pk),
                "pipelines-1-test": str(self.second_test.pk),
                "pipelines-1-pipeline_type": str(self.pipeline_type.pk),
                "pipelines-1-performed_date": "2026-08-31",
                "pipelines-1-performed_by": str(self.user.pk),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 pipelines created")

        pipelines = Pipeline.objects.select_related(
            "test",
            "type",
            "performed_by",
            "created_by",
        ).order_by("test_id")
        self.assertEqual(pipelines.count(), 2)
        self.assertEqual(pipelines[0].test, self.first_test)
        self.assertEqual(pipelines[0].type, self.pipeline_type)
        self.assertEqual(pipelines[0].performed_date, date(2026, 8, 31))
        self.assertEqual(pipelines[0].performed_by, self.user)
        self.assertEqual(pipelines[0].created_by, self.user)
        self.assertTrue(pipelines[0].statuses.filter(pk=self.default_status.pk).exists())
        self.assertEqual(pipelines[1].test, self.second_test)

    def test_bulk_pipeline_rows_reject_test_from_different_sample(self):
        response = self.client.post(
            reverse("lab:bulk_pipeline_create_form"),
            {
                "bulk_pipeline_action": "create",
                "pipelines-TOTAL_FORMS": "1",
                "pipelines-INITIAL_FORMS": "0",
                "pipelines-MIN_NUM_FORMS": "1",
                "pipelines-MAX_NUM_FORMS": "1000",
                "pipelines-0-individual": str(self.first.pk),
                "pipelines-0-sample": str(self.first_sample.pk),
                "pipelines-0-test": str(self.first_second_test.pk),
                "pipelines-0-pipeline_type": str(self.pipeline_type.pk),
                "pipelines-0-performed_date": "2026-08-31",
                "pipelines-0-performed_by": str(self.user.pk),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertEqual(Pipeline.objects.count(), 0)

    def test_bulk_pipeline_rows_do_not_create_partial_pipelines(self):
        response = self.client.post(
            reverse("lab:bulk_pipeline_create_form"),
            {
                "bulk_pipeline_action": "create",
                "pipelines-TOTAL_FORMS": "2",
                "pipelines-INITIAL_FORMS": "0",
                "pipelines-MIN_NUM_FORMS": "1",
                "pipelines-MAX_NUM_FORMS": "1000",
                "pipelines-0-individual": str(self.first.pk),
                "pipelines-0-sample": str(self.first_sample.pk),
                "pipelines-0-test": str(self.first_test.pk),
                "pipelines-0-pipeline_type": str(self.pipeline_type.pk),
                "pipelines-0-performed_date": "2026-08-31",
                "pipelines-0-performed_by": str(self.user.pk),
                "pipelines-1-individual": str(self.second.pk),
                "pipelines-1-sample": str(self.second_sample.pk),
                "pipelines-1-test": str(self.second_test.pk),
                "pipelines-1-pipeline_type": "",
                "pipelines-1-performed_date": "2026-08-31",
                "pipelines-1-performed_by": str(self.user.pk),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose a pipeline type.")
        self.assertEqual(Pipeline.objects.count(), 0)

    def test_bulk_pipeline_create_modal_requires_add_pipeline_permission(self):
        self.user.user_permissions.clear()

        response = self.client.get(reverse("lab:bulk_pipeline_create_modal"))

        self.assertEqual(response.status_code, 403)

    def test_bulk_pipeline_create_form_requires_add_pipeline_permission(self):
        self.user.user_permissions.clear()

        response = self.client.post(reverse("lab:bulk_pipeline_create_form"))

        self.assertEqual(response.status_code, 403)

    def test_bulk_pipeline_test_options_requires_add_pipeline_permission(self):
        self.user.user_permissions.clear()

        response = self.client.get(reverse("lab:bulk_pipeline_test_options"))

        self.assertEqual(response.status_code, 403)
