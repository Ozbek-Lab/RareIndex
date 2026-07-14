from datetime import date

from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User, Permission
from .htmx_views import (
    RevealSensitiveFieldView,
    individual_demographics_edit,
    individual_demographics_save,
    individual_identification_edit,
    individual_identification_save,
)
from .models import CrossIdentifier, IdentifierType, Individual
from .tables import IndividualTable
from .views import DashboardView, IndividualDetailView

class PIIRevealTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="normaluser", password="password")
        self.admin = User.objects.create_user(username="adminuser", password="password")
        perm = Permission.objects.get(codename="view_sensitive_data")
        self.admin.user_permissions.add(perm)
        self.change_perm = Permission.objects.get(codename="change_individual")
        self.user.user_permissions.add(self.change_perm)
        
        self.individual = Individual.objects.create(
            full_name="John Doe",
            tc_identity=12345678901,
            birth_date=date(2001, 2, 3),
            sex="male",
            created_by=self.user,
        )
        self.primary_type = IdentifierType.objects.create(
            name="RareBoost",
            use_priority=1,
            created_by=self.user,
        )
        self.secondary_type = IdentifierType.objects.create(
            name="Biobank",
            use_priority=2,
            created_by=self.user,
        )
        self.other_type = IdentifierType.objects.create(
            name="Other ID",
            use_priority=0,
            is_shown_in_table=True,
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.individual,
            id_type=self.primary_type,
            id_value="RB_SECRET",
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.individual,
            id_type=self.secondary_type,
            id_value="BIO_SECRET",
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.individual,
            id_type=self.other_type,
            id_value="OTHER_SECRET",
            created_by=self.user,
        )

    def test_table_render_without_permission(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = self.user
        
        table = IndividualTable([self.individual])
        table.request = request # Simulate SingleTableMixin behavior
        
        # Access the column. render_full_name is called by table.
        # We can call it directly to test logic.
        rendered = table.render_full_name("John Doe", self.individual)
        self.assertEqual(rendered, "*****")
        
    def test_table_render_with_permission(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = self.admin
        
        table = IndividualTable([self.individual])
        table.request = request 
        
        rendered = table.render_full_name("John Doe", self.individual)
        self.assertIn("fa-eye", rendered)
        self.assertIn("hx-get", rendered)
        
    def test_reveal_view_permission_denied(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = self.user

        response = RevealSensitiveFieldView.as_view()(
            request,
            "Individual",
            self.individual.pk,
            "full_name",
        )
        # The view returns a 200 with error message as span, OR 403?
        # My implementation: HttpResponse("<span>(Redacted - Permission Denied)</span>") (Status 200 by default)
        self.assertContains(response, "Redacted - Permission Denied")

    def test_reveal_view_success(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = self.admin

        response = RevealSensitiveFieldView.as_view()(
            request,
            "Individual",
            self.individual.pk,
            "full_name",
        )
        self.assertContains(response, "John Doe")
        self.assertContains(response, "x-data") # AlpineJS check

    def test_identification_edit_masks_sensitive_fields_without_sensitive_permission(self):
        user = User.objects.get(pk=self.user.pk)
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        response = individual_identification_edit(request, self.individual.pk)
        content = response.content.decode()

        self.assertContains(response, "*****")
        self.assertContains(response, "***********")
        self.assertNotIn("John Doe", content)
        self.assertNotIn("12345678901", content)
        self.assertIn("RB_SECRET", content)
        self.assertIn("BIO_SECRET", content)
        self.assertIn("OTHER_SECRET", content)

    def test_identification_save_preserves_sensitive_fields_without_sensitive_permission(self):
        user = User.objects.get(pk=self.user.pk)
        factory = RequestFactory()
        request = factory.post("/", {
            "full_name": "Leaked Edit",
            "tc_identity": "99999999999",
            "primary_id": "RB_2025_999.9",
            "secondary_id": "RD3.F999.9",
            "cross_identifiers_json": '[{"type_id": "%s", "value": "OTHER_CHANGED"}]' % self.other_type.pk,
        })
        request.user = user

        response = individual_identification_save(request, self.individual.pk)
        self.assertEqual(response.status_code, 200)

        self.individual.refresh_from_db()
        self.assertEqual(self.individual.full_name, "John Doe")
        self.assertEqual(self.individual.tc_identity, 12345678901)
        self.assertTrue(
            CrossIdentifier.objects.filter(
                individual=self.individual,
                id_type=self.primary_type,
                id_value="RB_2025_999.9",
            ).exists()
        )
        self.assertTrue(
            CrossIdentifier.objects.filter(
                individual=self.individual,
                id_type=self.secondary_type,
                id_value="RD3.F999.9",
            ).exists()
        )
        self.assertTrue(
            CrossIdentifier.objects.filter(
                individual=self.individual,
                id_type=self.other_type,
                id_value="OTHER_CHANGED",
            ).exists()
        )

    def test_demographics_edit_masks_birth_date_without_sensitive_permission(self):
        user = User.objects.get(pk=self.user.pk)
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        response = individual_demographics_edit(request, self.individual.pk)
        content = response.content.decode()

        self.assertContains(response, "**-**-****")
        self.assertNotIn("2001-02-03", content)
        self.assertNotIn("Feb.", content)

    def test_demographics_save_preserves_birth_date_without_sensitive_permission(self):
        user = User.objects.get(pk=self.user.pk)
        factory = RequestFactory()
        request = factory.post("/", {
            "sex": "female",
            "birth_date": "2020-01-01",
            "vital_status": "deceased",
            "family": "",
        })
        request.user = user

        response = individual_demographics_save(request, self.individual.pk)
        self.assertEqual(response.status_code, 200)

        self.individual.refresh_from_db()
        self.assertEqual(self.individual.birth_date, date(2001, 2, 3))
        self.assertEqual(self.individual.sex, "female")
        self.assertFalse(self.individual.is_alive)

    def test_individual_history_masks_sensitive_diffs_without_sensitive_permission(self):
        self.individual.full_name = "Jane Doe"
        self.individual.tc_identity = 99999999999
        self.individual.birth_date = date(2020, 1, 1)
        self.individual.save()

        user = User.objects.get(pk=self.user.pk)
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        history = list(self.individual.history.all()[:2])
        view = IndividualDetailView()
        view.request = request
        diff = view._get_field_diff(history[0], history[1])
        diff_text = " ".join(diff.values())

        self.assertEqual(diff["Full Name"], "'*****' -> '*****'")
        self.assertEqual(diff["Tc Identity"], "'***********' -> '***********'")
        self.assertEqual(diff["Birth Date"], "'**-**-****' -> '**-**-****'")
        self.assertNotIn("John Doe", diff_text)
        self.assertNotIn("Jane Doe", diff_text)
        self.assertNotIn("12345678901", diff_text)
        self.assertNotIn("99999999999", diff_text)
        self.assertNotIn("2001-02-03", diff_text)
        self.assertNotIn("2020-01-01", diff_text)

    def test_dashboard_recent_activity_masks_sensitive_individual_diffs_without_permission(self):
        self.individual.full_name = "Jane Doe"
        self.individual.tc_identity = 99999999999
        self.individual.birth_date = date(2020, 1, 1)
        self.individual.save()

        user = User.objects.get(pk=self.user.pk)
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user

        view = DashboardView()
        view.setup(request)
        context = view.get_context_data()
        item = next(
            item
            for item in context["news_feed"]
            if item.safe_model_name == "Individual" and item.history_type == "~"
        )
        diff_text = " ".join(item.diff_display.values())

        self.assertEqual(item.diff_display["full_name"], "'*****' -> '*****'")
        self.assertEqual(item.diff_display["tc_identity"], "'***********' -> '***********'")
        self.assertEqual(item.diff_display["birth_date"], "'**-**-****' -> '**-**-****'")
        self.assertNotIn("John Doe", diff_text)
        self.assertNotIn("Jane Doe", diff_text)
        self.assertNotIn("12345678901", diff_text)
        self.assertNotIn("99999999999", diff_text)
        self.assertNotIn("2001-02-03", diff_text)
        self.assertNotIn("2020-01-01", diff_text)
