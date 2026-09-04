from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.test import TestCase
from django.test import override_settings
from django.template.loader import render_to_string
from django.urls import reverse

from lab.forms import parse_bulk_create_id_text
from lab.models import (
    CrossIdentifier,
    IdentifierType,
    Individual,
    Project,
    ProjectMembership,
    Sample,
    SampleType,
    Status,
)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    MIDDLEWARE=[
        middleware
        for middleware in settings.MIDDLEWARE
        if middleware != "reversion.middleware.RevisionMiddleware"
    ],
)
class BulkSampleCreateModalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bulk-sample-user", password="password")
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Sample),
                codename="add_sample",
            )
        )
        self.client.force_login(self.user)
        self.sample_type = SampleType.objects.create(
            name="Blood",
            created_by=self.user,
        )
        self.second_sample_type = SampleType.objects.create(
            name="Saliva",
            created_by=self.user,
        )
        self.unused_sample_type = SampleType.objects.create(
            name="Tissue",
            created_by=self.user,
        )
        self.planned_status = Status.objects.create(
            name="Planned",
            content_type=ContentType.objects.get_for_model(Sample),
            created_by=self.user,
        )

        self.id_type = IdentifierType.objects.create(
            name="RareBoost",
            use_priority=1,
            created_by=self.user,
        )
        self.first = Individual.objects.create(full_name="First Individual", created_by=self.user)
        self.second = Individual.objects.create(full_name="Second Individual", created_by=self.user)
        self.project = Project.objects.create(name="Bulk Sample Project", created_by=self.user)
        self.project.individuals.add(self.first, self.second)
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ProjectMembership.Role.EDITOR,
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.first,
            id_type=self.id_type,
            id_value="RB_2026_001.1",
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.second,
            id_type=self.id_type,
            id_value="RB_2026_002.1",
            created_by=self.user,
        )
        self.existing_first_sample = Sample.objects.create(
            individual=self.first,
            sample_type=self.sample_type,
            created_by=self.user,
        )
        self.existing_second_sample = Sample.objects.create(
            individual=self.second,
            sample_type=self.second_sample_type,
            created_by=self.user,
        )
        self.existing_sample_ids = {
            self.existing_first_sample.pk,
            self.existing_second_sample.pk,
        }

    def test_bulk_create_id_parser_splits_common_delimiters(self):
        value = " RB_2026_001.1,\tRB_2026_002.1\nRB_2026_003.1  RB_2026_004.1, "

        self.assertEqual(
            parse_bulk_create_id_text(value),
            [
                "RB_2026_001.1",
                "RB_2026_002.1",
                "RB_2026_003.1",
                "RB_2026_004.1",
            ],
        )

    def test_bulk_create_dropdown_renders_sample_modal_url(self):
        html = render_to_string("lab/components/bulk_create_dropdown.html")

        self.assertIn(reverse("lab:bulk_sample_create_modal"), html)

    def test_samples_bulk_create_modal_returns_matching_individual_ids(self):
        url = reverse("lab:bulk_sample_create_modal")

        response = self.client.post(
            url,
            {"ids": "RB_2026_001.1, missing-id\nRB_2026_002.1"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.first.pk))
        self.assertContains(response, "RB_2026_001.1")
        self.assertContains(response, str(self.second.pk))
        self.assertContains(response, "RB_2026_002.1")
        self.assertContains(response, "2 found")
        self.assertNotContains(response, "Object ID")

    def test_samples_lookup_result_includes_add_samples_button(self):
        response = self.client.post(
            reverse("lab:bulk_sample_create_modal"),
            {"ids": "RB_2026_001.1 RB_2026_002.1"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add Samples")
        self.assertContains(response, reverse("lab:bulk_sample_create_form"))
        self.assertContains(response, f'name="individual_ids" value="{self.first.pk}"')
        self.assertContains(response, f'name="individual_ids" value="{self.second.pk}"')

    def test_add_samples_button_renders_bulk_sample_rows(self):
        response = self.client.post(
            reverse("lab:bulk_sample_create_form"),
            {"individual_ids": [str(self.first.pk), str(self.second.pk)]},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Samples")
        self.assertContains(response, str(self.first.pk))
        self.assertContains(response, "RB_2026_001.1")
        self.assertContains(response, str(self.second.pk))
        self.assertContains(response, "RB_2026_002.1")
        self.assertContains(response, "samples-0-sample_type")
        self.assertContains(response, "samples-1-sample_type")
        self.assertNotContains(response, "Object ID")

    def test_bulk_sample_rows_only_show_sample_types_from_each_individual_samples(self):
        response = self.client.post(
            reverse("lab:bulk_sample_create_form"),
            {"individual_ids": [str(self.first.pk), str(self.second.pk)]},
            HTTP_HX_REQUEST="true",
        )

        html = response.content.decode()
        first_select = html.split('id="id_samples-0-sample_type"', 1)[1].split(
            "</select>", 1
        )[0]
        second_select = html.split('id="id_samples-1-sample_type"', 1)[1].split(
            "</select>", 1
        )[0]

        self.assertIn("Blood", first_select)
        self.assertNotIn("Saliva", first_select)
        self.assertNotIn("Tissue", first_select)
        self.assertIn("Saliva", second_select)
        self.assertNotIn("Blood", second_select)
        self.assertNotIn("Tissue", second_select)

    def test_bulk_sample_rows_create_samples_with_required_fields(self):
        response = self.client.post(
            reverse("lab:bulk_sample_create_form"),
            {
                "bulk_sample_action": "create",
                "samples-TOTAL_FORMS": "2",
                "samples-INITIAL_FORMS": "0",
                "samples-MIN_NUM_FORMS": "1",
                "samples-MAX_NUM_FORMS": "1000",
                "samples-0-individual": str(self.first.pk),
                "samples-0-sample_type": str(self.sample_type.pk),
                "samples-1-individual": str(self.second.pk),
                "samples-1-sample_type": str(self.second_sample_type.pk),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 samples created")

        samples = Sample.objects.exclude(pk__in=self.existing_sample_ids).order_by(
            "individual_id"
        )
        self.assertEqual(samples.count(), 2)
        self.assertEqual(samples[0].individual, self.first)
        self.assertEqual(samples[0].sample_type, self.sample_type)
        self.assertEqual(samples[0].created_by, self.user)
        self.assertTrue(samples[0].statuses.filter(pk=self.planned_status.pk).exists())
        self.assertEqual(samples[1].individual, self.second)
        self.assertEqual(samples[1].sample_type, self.second_sample_type)

    def test_bulk_sample_rows_reject_unavailable_sample_type_for_row(self):
        response = self.client.post(
            reverse("lab:bulk_sample_create_form"),
            {
                "bulk_sample_action": "create",
                "samples-TOTAL_FORMS": "2",
                "samples-INITIAL_FORMS": "0",
                "samples-MIN_NUM_FORMS": "1",
                "samples-MAX_NUM_FORMS": "1000",
                "samples-0-individual": str(self.first.pk),
                "samples-0-sample_type": str(self.unused_sample_type.pk),
                "samples-1-individual": str(self.second.pk),
                "samples-1-sample_type": str(self.second_sample_type.pk),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertEqual(Sample.objects.count(), len(self.existing_sample_ids))

    def test_bulk_sample_rows_do_not_create_partial_samples(self):
        response = self.client.post(
            reverse("lab:bulk_sample_create_form"),
            {
                "bulk_sample_action": "create",
                "samples-TOTAL_FORMS": "2",
                "samples-INITIAL_FORMS": "0",
                "samples-MIN_NUM_FORMS": "1",
                "samples-MAX_NUM_FORMS": "1000",
                "samples-0-individual": str(self.first.pk),
                "samples-0-sample_type": str(self.sample_type.pk),
                "samples-1-individual": str(self.second.pk),
                "samples-1-sample_type": "",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose a sample type.")
        self.assertEqual(Sample.objects.count(), len(self.existing_sample_ids))

    def test_samples_bulk_create_modal_requires_add_sample_permission(self):
        self.user.user_permissions.clear()

        response = self.client.get(reverse("lab:bulk_sample_create_modal"))

        self.assertEqual(response.status_code, 403)

    def test_bulk_sample_create_form_requires_add_sample_permission(self):
        self.user.user_permissions.clear()

        response = self.client.post(reverse("lab:bulk_sample_create_form"))

        self.assertEqual(response.status_code, 403)
