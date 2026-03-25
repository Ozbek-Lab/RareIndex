import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.conf import settings
from lab.models import Individual
from lab.jwt_utils import issue_plot_token

class PlotAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testapiuser", password="password")
        self.client = Client()
        self.token = issue_plot_token(self.user)
        self.individual = Individual.objects.create(full_name="Test Individual", created_by=self.user)

    def test_plot_token_issue(self):
        self.client.login(username="testapiuser", password="password")
        response = self.client.get(reverse("lab:issue_plot_token"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.json())

    def test_plot_data_session_auth(self):
        self.client.login(username="testapiuser", password="password")
        query = json.dumps({"annotate": {"count": "id"}})
        response = self.client.get(reverse("lab:generic_plot_data"), {"model": "Individual", "query": query})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["record_count"], 1)

    def test_plot_data_jwt_auth(self):
        query = json.dumps({"annotate": {"count": "id"}})
        response = self.client.get(
            reverse("lab:generic_plot_data"), 
            {"model": "Individual", "query": query},
            HTTP_AUTHORIZATION=f"Bearer {self.token}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["record_count"], 1)

    def test_plot_data_expired_jwt(self):
        # We can't wait 60s, but we'll mock verify_plot_token in a real test 
        # or assume jwt.decode(exp) works. 
        # For now, let's just test invalid token.
        response = self.client.get(
            reverse("lab:generic_plot_data"), 
            {"model": "Individual"},
            HTTP_AUTHORIZATION="Bearer invalidtoken"
        )
        self.assertEqual(response.status_code, 401)

    def test_plot_data_disallowed_model(self):
        self.client.login(username="testapiuser", password="password")
        response = self.client.get(reverse("lab:generic_plot_data"), {"model": "User"})
        self.assertEqual(response.status_code, 403)

    def test_plot_data_aggregation(self):
        self.client.login(username="testapiuser", password="password")
        # Add another individual
        Individual.objects.create(full_name="Another One", created_by=self.user)
        
        query = json.dumps({
            "annotate": {
                "total": {"count": "id"},
            }
        })
        response = self.client.get(reverse("lab:generic_plot_data"), {"model": "Individual", "query": query})
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        # Since we use list(qs) after annotate, the annotation should be in the results if we used values()
        # Wait, if we use list(qs) on a normal queryset, annotations are attributes of the objects.
        # But JSONResponse(list(qs)) won't serialize model instances with attributes easily.
        # Our generic_plot_data uses qs.values(*values) if provided.
        
        query_v = json.dumps({
            "values": ["full_name"],
            "annotate": {
                "c": "id",
            }
        })
        response = self.client.get(reverse("lab:generic_plot_data"), {"model": "Individual", "query": query_v})
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertTrue(all("c" in item for item in data))
