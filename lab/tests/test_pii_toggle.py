from django.test import TestCase, Client
from django.contrib.auth.models import User, Permission
from django.urls import reverse
from lab.models import Individual, Status

class PIIToggleTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.admin = User.objects.create_user(username="adminuser", password="password")
        perm = Permission.objects.get(codename="view_sensitive_data")
        self.admin.user_permissions.add(perm)
        
        self.status = Status.objects.create(name="Active", created_by=self.user)
        
        self.individual = Individual.objects.create(
            full_name="Jane Doe",
            birth_date="1990-01-01",
            sex="female",
            created_by=self.user,
            status=self.status,
        )
        
        self.client = Client()

    def test_reveal_action_shows_hide_button(self):
        self.client.force_login(self.admin)
        url = reverse("lab:reveal_sensitive_field", kwargs={
            "model_name": "Individual",
            "pk": self.individual.pk,
            "field_name": "full_name"
        })
        
        # Default action is reveal
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Jane Doe", content)
        self.assertIn("action=hide", content)
        self.assertIn("fa-eye-slash", content) # FontAwesome icon for hide

    def test_hide_action_shows_reveal_button(self):
        self.client.force_login(self.admin)
        url = reverse("lab:reveal_sensitive_field", kwargs={
            "model_name": "Individual",
            "pk": self.individual.pk,
            "field_name": "full_name"
        })
        
        # Request hide action
        response = self.client.get(url, {"action": "hide"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("*****", content)
        self.assertNotIn("Jane Doe", content)
        self.assertIn("fa-eye", content)
        self.assertNotIn("action=hide", content) # The reveal link shouldn't have action=hide

    def test_hide_birth_date_mask(self):
        self.client.force_login(self.admin)
        url = reverse("lab:reveal_sensitive_field", kwargs={
            "model_name": "Individual",
            "pk": self.individual.pk,
            "field_name": "birth_date"
        })
        
        response = self.client.get(url, {"action": "hide"})
        content = response.content.decode()
        self.assertIn("**-**-****", content)
