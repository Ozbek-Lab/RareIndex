from django.contrib.auth.models import Permission, User
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase

from .htmx_views import (
    project_delete_modal,
    project_individual_add,
    project_individual_remove,
    project_individual_search,
)
from .models import CrossIdentifier, IdentifierType, Individual, Project


class ProjectPermissionTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="viewer", password="password")
        self.editor = User.objects.create_user(username="editor", password="password")
        self.deleter = User.objects.create_user(username="deleter", password="password")
        self.editor.user_permissions.add(Permission.objects.get(codename="change_project"))
        self.deleter.user_permissions.add(Permission.objects.get(codename="delete_project"))

        self.project = Project.objects.create(name="IEM", created_by=self.user)
        self.individual = Individual.objects.create(
            full_name="John Doe",
            sex="male",
            created_by=self.user,
        )
        self.primary_type = IdentifierType.objects.create(
            name="RareBoost",
            use_priority=1,
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.individual,
            id_type=self.primary_type,
            id_value="RB_2025_1.1",
            created_by=self.user,
        )

    def _request(self, method="get", user=None, path="/"):
        request = getattr(self.factory, method)(path)
        request.user = user or self.user
        return request

    def test_project_delete_button_requires_delete_project_permission(self):
        request = self._request(user=self.user)
        html = render_to_string(
            "lab/project_detail.html",
            {
                "project": self.project,
                "project_individuals_sort": "added",
                "project_individuals_dir": "desc",
                "project_individuals_search": "",
                "individual_page": Paginator([], 25).get_page(1),
            },
            request=request,
        )

        self.assertNotIn("project_delete_modal", html)
        self.assertNotIn(f"/htmx/project/{self.project.pk}/delete/", html)

        request = self._request(user=self.deleter)
        html = render_to_string(
            "lab/project_detail.html",
            {
                "project": self.project,
                "project_individuals_sort": "added",
                "project_individuals_dir": "desc",
                "project_individuals_search": "",
                "individual_page": Paginator([], 25).get_page(1),
            },
            request=request,
        )

        self.assertIn(f"/htmx/project/{self.project.pk}/delete/", html)

    def test_project_individual_remove_button_requires_change_project_permission(self):
        self.project.individuals.add(self.individual)
        page = Paginator([self.individual], 25).get_page(1)

        request = self._request(user=self.user)
        html = render_to_string(
            "lab/partials/project_individual_rows.html",
            {"project": self.project, "individual_page": page},
            request=request,
        )

        self.assertNotIn("project_individual_remove", html)
        self.assertNotIn(f"/htmx/project/{self.project.pk}/individuals/{self.individual.pk}/remove/", html)

        request = self._request(user=self.editor)
        html = render_to_string(
            "lab/partials/project_individual_rows.html",
            {"project": self.project, "individual_page": page},
            request=request,
        )

        self.assertIn(f"/htmx/project/{self.project.pk}/individuals/{self.individual.pk}/remove/", html)

    def test_project_membership_endpoints_require_change_project_permission(self):
        response = project_individual_search(
            self._request(user=self.user, path="/?search=RB_2025"),
            self.project.pk,
        )
        self.assertEqual(response.status_code, 403)

        response = project_individual_add(
            self._request(method="post", user=self.user),
            self.project.pk,
            self.individual.pk,
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.project.individuals.filter(pk=self.individual.pk).exists())

        self.project.individuals.add(self.individual)
        response = project_individual_remove(
            self._request(method="delete", user=self.user),
            self.project.pk,
            self.individual.pk,
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.project.individuals.filter(pk=self.individual.pk).exists())

    def test_project_membership_endpoints_allow_change_project_permission(self):
        response = project_individual_add(
            self._request(method="post", user=self.editor),
            self.project.pk,
            self.individual.pk,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.project.individuals.filter(pk=self.individual.pk).exists())

        response = project_individual_remove(
            self._request(method="delete", user=self.editor),
            self.project.pk,
            self.individual.pk,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.project.individuals.filter(pk=self.individual.pk).exists())

    def test_project_delete_endpoint_requires_delete_project_permission(self):
        response = project_delete_modal(self._request(user=self.user), self.project.pk)
        self.assertEqual(response.status_code, 403)

        response = project_delete_modal(self._request(user=self.deleter), self.project.pk)
        self.assertEqual(response.status_code, 200)
