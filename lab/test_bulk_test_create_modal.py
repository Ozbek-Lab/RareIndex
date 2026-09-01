from datetime import date

from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.test import override_settings
from django.template.loader import render_to_string
from django.urls import reverse

from lab.models import (
    CrossIdentifier,
    IdentifierType,
    Individual,
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
class BulkTestCreateModalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bulk-test-user", password="password")
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(LabTest),
                codename="add_test",
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
        self.default_status = Status.objects.create(
            name="Waiting Data/Bioinformatic process",
            content_type=ContentType.objects.get_for_model(LabTest),
            created_by=self.user,
        )

        self.first = Individual.objects.create(full_name="First Individual", created_by=self.user)
        self.second = Individual.objects.create(full_name="Second Individual", created_by=self.user)
        self.no_sample = Individual.objects.create(
            full_name="No Sample Individual",
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.first,
            id_type=self.id_type,
            id_value="RB_2026_101.1",
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.second,
            id_type=self.id_type,
            id_value="RB_2026_102.1",
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.no_sample,
            id_type=self.id_type,
            id_value="RB_2026_103.1",
            created_by=self.user,
        )

        self.first_sample = Sample.objects.create(
            individual=self.first,
            sample_type=self.blood_type,
            receipt_date=date(2026, 1, 15),
            created_by=self.user,
        )
        self.second_sample = Sample.objects.create(
            individual=self.second,
            sample_type=self.saliva_type,
            created_by=self.user,
        )

    def test_bulk_create_dropdown_renders_test_modal_url(self):
        html = render_to_string("lab/components/bulk_create_dropdown.html")

        self.assertIn(reverse("lab:bulk_test_create_modal"), html)

    def test_bulk_test_create_modal_returns_matching_individual_ids(self):
        response = self.client.post(
            reverse("lab:bulk_test_create_modal"),
            {"ids": "RB_2026_101.1, missing-id\nRB_2026_102.1"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bulk Create Tests")
        self.assertContains(response, "Add Tests")
        self.assertContains(response, str(self.first.pk))
        self.assertContains(response, "RB_2026_101.1")
        self.assertContains(response, str(self.second.pk))
        self.assertContains(response, "RB_2026_102.1")
        self.assertContains(response, f'name="individual_ids" value="{self.first.pk}"')
        self.assertContains(response, f'name="individual_ids" value="{self.second.pk}"')
        self.assertNotContains(response, "Object ID")

    def test_add_tests_button_renders_bulk_test_rows(self):
        response = self.client.post(
            reverse("lab:bulk_test_create_form"),
            {"individual_ids": [str(self.first.pk), str(self.second.pk)]},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Tests")
        self.assertContains(response, str(self.first.pk))
        self.assertContains(response, "RB_2026_101.1")
        self.assertContains(response, str(self.second.pk))
        self.assertContains(response, "RB_2026_102.1")
        self.assertContains(response, "tests-0-sample")
        self.assertContains(response, "tests-0-test_type")
        self.assertContains(response, "tests-1-sample")
        self.assertContains(response, "tests-1-test_type")
        self.assertNotContains(response, "Object ID")

    def test_bulk_test_rows_only_show_samples_from_each_individual(self):
        response = self.client.post(
            reverse("lab:bulk_test_create_form"),
            {"individual_ids": [str(self.first.pk), str(self.second.pk)]},
            HTTP_HX_REQUEST="true",
        )

        html = response.content.decode()
        first_select = html.split('id="id_tests-0-sample"', 1)[1].split(
            "</select>", 1
        )[0]
        second_select = html.split('id="id_tests-1-sample"', 1)[1].split(
            "</select>", 1
        )[0]

        self.assertIn(f"value=\"{self.first_sample.pk}\"", first_select)
        self.assertIn("#%s - Blood - 2026-01-15" % self.first_sample.pk, first_select)
        self.assertNotIn(f"value=\"{self.second_sample.pk}\"", first_select)
        self.assertIn(f"value=\"{self.second_sample.pk}\"", second_select)
        self.assertIn("#%s - Saliva - No receipt date" % self.second_sample.pk, second_select)
        self.assertNotIn(f"value=\"{self.first_sample.pk}\"", second_select)

    def test_bulk_test_rows_warn_when_an_individual_has_no_samples(self):
        response = self.client.post(
            reverse("lab:bulk_test_create_form"),
            {"individual_ids": [str(self.no_sample.pk)]},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This individual has no samples.")
        self.assertContains(response, "Create Tests")
        self.assertContains(response, "disabled")

    def test_bulk_test_rows_create_tests_with_required_fields(self):
        response = self.client.post(
            reverse("lab:bulk_test_create_form"),
            {
                "bulk_test_action": "create",
                "tests-TOTAL_FORMS": "2",
                "tests-INITIAL_FORMS": "0",
                "tests-MIN_NUM_FORMS": "1",
                "tests-MAX_NUM_FORMS": "1000",
                "tests-0-individual": str(self.first.pk),
                "tests-0-sample": str(self.first_sample.pk),
                "tests-0-test_type": str(self.wgs_type.pk),
                "tests-1-individual": str(self.second.pk),
                "tests-1-sample": str(self.second_sample.pk),
                "tests-1-test_type": str(self.wes_type.pk),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 tests created")

        tests = LabTest.objects.select_related("sample", "test_type", "created_by").order_by(
            "sample_id"
        )
        self.assertEqual(tests.count(), 2)
        self.assertEqual(tests[0].sample, self.first_sample)
        self.assertEqual(tests[0].test_type, self.wgs_type)
        self.assertEqual(tests[0].created_by, self.user)
        self.assertTrue(tests[0].statuses.filter(pk=self.default_status.pk).exists())
        self.assertEqual(tests[1].sample, self.second_sample)
        self.assertEqual(tests[1].test_type, self.wes_type)

    def test_bulk_test_rows_reject_sample_from_different_individual(self):
        response = self.client.post(
            reverse("lab:bulk_test_create_form"),
            {
                "bulk_test_action": "create",
                "tests-TOTAL_FORMS": "2",
                "tests-INITIAL_FORMS": "0",
                "tests-MIN_NUM_FORMS": "1",
                "tests-MAX_NUM_FORMS": "1000",
                "tests-0-individual": str(self.first.pk),
                "tests-0-sample": str(self.second_sample.pk),
                "tests-0-test_type": str(self.wgs_type.pk),
                "tests-1-individual": str(self.second.pk),
                "tests-1-sample": str(self.second_sample.pk),
                "tests-1-test_type": str(self.wes_type.pk),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertEqual(LabTest.objects.count(), 0)

    def test_bulk_test_rows_do_not_create_partial_tests(self):
        response = self.client.post(
            reverse("lab:bulk_test_create_form"),
            {
                "bulk_test_action": "create",
                "tests-TOTAL_FORMS": "2",
                "tests-INITIAL_FORMS": "0",
                "tests-MIN_NUM_FORMS": "1",
                "tests-MAX_NUM_FORMS": "1000",
                "tests-0-individual": str(self.first.pk),
                "tests-0-sample": str(self.first_sample.pk),
                "tests-0-test_type": str(self.wgs_type.pk),
                "tests-1-individual": str(self.second.pk),
                "tests-1-sample": str(self.second_sample.pk),
                "tests-1-test_type": "",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose a test type.")
        self.assertEqual(LabTest.objects.count(), 0)

    def test_bulk_test_create_modal_requires_add_test_permission(self):
        self.user.user_permissions.clear()

        response = self.client.get(reverse("lab:bulk_test_create_modal"))

        self.assertEqual(response.status_code, 403)

    def test_bulk_test_create_form_requires_add_test_permission(self):
        self.user.user_permissions.clear()

        response = self.client.post(reverse("lab:bulk_test_create_form"))

        self.assertEqual(response.status_code, 403)
