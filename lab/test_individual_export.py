import csv
import io

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import CrossIdentifier, IdentifierType, Individual


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class IndividualExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="individual-export-user")
        permission = Permission.objects.get(
            content_type=ContentType.objects.get_for_model(Individual),
            codename="view_sensitive_data",
        )
        cls.user.user_permissions.add(permission)

        primary_type = IdentifierType.objects.create(
            name="Primary",
            use_priority=1,
            created_by=cls.user,
        )
        cls.filtered_individual = Individual.objects.create(
            full_name="Filtered Person",
            sex="male",
            created_by=cls.user,
        )
        cls.other_individual = Individual.objects.create(
            full_name="Other Person",
            sex="female",
            created_by=cls.user,
        )
        CrossIdentifier.objects.create(
            individual=cls.filtered_individual,
            id_type=primary_type,
            id_value="FILTERED-1",
            created_by=cls.user,
        )
        CrossIdentifier.objects.create(
            individual=cls.other_individual,
            id_type=primary_type,
            id_value="OTHER-1",
            created_by=cls.user,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _export_rows(self, params):
        response = self.client.get(reverse("lab:individual_export"), params)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8-sig")
        return list(csv.reader(io.StringIO(content)))

    def test_export_applies_current_filter_params(self):
        rows = self._export_rows({"sex": "male"})

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "FILTERED-1")

    def test_export_search_matches_sensitive_name_search_from_list_view(self):
        rows = self._export_rows({"search": "Filtered Person"})

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "FILTERED-1")

    def test_export_button_uses_live_location_search_on_click(self):
        response = self.client.get(reverse("lab:individual_list"), {"sex": "male"})
        html = response.content.decode()
        export_url = reverse("lab:individual_export")

        self.assertIn(f'href="{export_url}?sex=male"', html)
        self.assertIn(
            f"@click=\"$event.currentTarget.href = '{export_url}' + window.location.search\"",
            html,
        )
