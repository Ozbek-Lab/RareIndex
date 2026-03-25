from django.test import TestCase
from django.urls import reverse
from lab.models import PlotTemplate, DashboardWidget
from django.contrib.auth import get_user_model
import json

User = get_user_model()

class GalleryDashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.staff_user = User.objects.create_user(username="staff", password="password", is_staff=True)
        
        # Create templates
        self.published_tpl = PlotTemplate.objects.create(
            name="Published Chart",
            slug="published-chart",
            description="A chart",
            target_model="Individual",
            query_config={"values": ["status"]},
            notebook_filename="sunburst.py",
            is_published=True,
            created_by=self.staff_user,
        )
        self.draft_tpl = PlotTemplate.objects.create(
            name="Draft Chart",
            slug="draft-chart",
            description="WIP",
            target_model="Individual",
            query_config={},
            notebook_filename="status_bar.py",
            is_published=False,
            created_by=self.staff_user,
        )

    def test_gallery_shows_only_published(self):
        self.client.login(username="testuser", password="password")
        response = self.client.get(reverse("lab:plot_gallery"))
        self.assertEqual(response.status_code, 200)
        templates = response.context["templates"]
        self.assertIn(self.published_tpl, templates)
        self.assertNotIn(self.draft_tpl, templates)

    def test_add_and_remove_dashboard_widget(self):
        self.client.login(username="testuser", password="password")
        
        # Add widget
        response = self.client.post(reverse("lab:add_widget", args=[self.published_tpl.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(DashboardWidget.objects.filter(user=self.user, template=self.published_tpl).exists())
        
        widget = DashboardWidget.objects.get(user=self.user, template=self.published_tpl)
        
        # Remove widget
        response = self.client.post(reverse("lab:remove_widget", args=[widget.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DashboardWidget.objects.filter(user=self.user, template=self.published_tpl).exists())

    def test_reorder_dashboard_widgets(self):
        self.client.login(username="testuser", password="password")
        
        # Create two widgets
        w1 = DashboardWidget.objects.create(user=self.user, template=self.published_tpl, order=0)
        # We need a second template to create a second widget
        tpl2 = PlotTemplate.objects.create(
            name="T2",
            slug="t2-template",
            target_model="Individual",
            notebook_filename="status_bar.py",
            created_by=self.staff_user,
        )
        w2 = DashboardWidget.objects.create(user=self.user, template=tpl2, order=1)
        
        # Reorder sending w2 before w1
        new_order = [w2.pk, w1.pk]
        response = self.client.patch(
            reverse("lab:reorder_widgets"),
            data=json.dumps({"order": new_order}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        
        w1.refresh_from_db()
        w2.refresh_from_db()
        self.assertEqual(w2.order, 0)
        self.assertEqual(w1.order, 1)

    def test_non_staff_cannot_create_templates(self):
        # Even though admin is handled by Django, we can check basic access to the model's admin page
        self.client.login(username="testuser", password="password")
        response = self.client.get("/admin/lab/plottemplate/add/")
        # Should redirect to admin login because it's non-staff
        self.assertRedirects(response, "/admin/login/?next=/admin/lab/plottemplate/add/")
