from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from .models import Individual, AuditLog, Status
from .tables import IndividualTable

class PIIRevealTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="normaluser", password="password")
        self.admin = User.objects.create_user(username="adminuser", password="password")
        perm = Permission.objects.get(codename="view_sensitive_data")
        self.admin.user_permissions.add(perm)
        
        self.status = Status.objects.create(name="Active", created_by=self.user)
        
        self.individual = Individual.objects.create(
            full_name="John Doe",
            sex="male",
            created_by=self.user,
            status=self.status
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
        self.assertIn("Reveal", rendered)
        self.assertIn("hx-get", rendered)
        
    def test_reveal_view_permission_denied(self):
        self.client.login(username="normaluser", password="password")
        url = reverse("lab:reveal_sensitive_field", kwargs={
            "model_name": "Individual",
            "pk": self.individual.pk,
            "field_name": "full_name"
        })
        response = self.client.get(url)
        # The view returns a 200 with error message as span, OR 403?
        # My implementation: HttpResponse("<span>(Redacted - Permission Denied)</span>") (Status 200 by default)
        self.assertContains(response, "Redacted - Permission Denied")
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_reveal_view_success(self):
        self.client.login(username="adminuser", password="password")
        url = reverse("lab:reveal_sensitive_field", kwargs={
            "model_name": "Individual",
            "pk": self.individual.pk,
            "field_name": "full_name"
        })
        response = self.client.get(url)
        self.assertContains(response, "John Doe")
        self.assertContains(response, "x-data") # AlpineJS check
        
        # Check AuditLog
        self.assertEqual(AuditLog.objects.count(), 1)
        log = AuditLog.objects.first()
        self.assertEqual(log.user, self.admin)
        self.assertEqual(log.object_id, self.individual.pk)
        self.assertEqual(log.details['field'], 'full_name')
