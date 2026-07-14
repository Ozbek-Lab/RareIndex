from django.contrib.auth.models import Permission, User
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase

from .htmx_views import individual_parents_edit, individual_parents_save
from .models import CrossIdentifier, Family, IdentifierType, Individual


class FamilyParentPermissionTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.viewer = User.objects.create_user(username="viewer", password="password")
        self.family_editor = User.objects.create_user(username="family_editor", password="password")
        self.family_editor.user_permissions.add(Permission.objects.get(codename="change_family"))

        self.family = Family.objects.create(family_id="FAM-1", created_by=self.viewer)
        self.child = Individual.objects.create(
            full_name="Child",
            sex="female",
            family=self.family,
            is_index=True,
            is_affected=True,
            created_by=self.viewer,
        )
        self.father = Individual.objects.create(
            full_name="Father",
            sex="male",
            family=self.family,
            created_by=self.viewer,
        )
        self.mother = Individual.objects.create(
            full_name="Mother",
            sex="female",
            family=self.family,
            created_by=self.viewer,
        )
        self.primary_type = IdentifierType.objects.create(
            name="RareBoost",
            use_priority=1,
            created_by=self.viewer,
        )
        for individual, value in (
            (self.child, "RB_2025_1.1"),
            (self.father, "RB_2025_1.2"),
            (self.mother, "RB_2025_1.3"),
        ):
            CrossIdentifier.objects.create(
                individual=individual,
                id_type=self.primary_type,
                id_value=value,
                created_by=self.viewer,
            )

    def _request(self, method="get", user=None, data=None):
        request = getattr(self.factory, method)("/", data=data or {})
        request.user = user or self.viewer
        return request

    def test_parent_edit_button_requires_change_family_permission(self):
        request = self._request(user=self.viewer)
        html = render_to_string(
            "lab/partials/family_member_row.html",
            {
                "member": self.child,
                "individual": self.child,
                "edit_mode": False,
            },
            request=request,
        )

        self.assertNotIn(f"/htmx/individual/{self.child.pk}/parents/edit/", html)
        self.assertNotIn("Edit parents", html)

        request = self._request(user=self.family_editor)
        html = render_to_string(
            "lab/partials/family_member_row.html",
            {
                "member": self.child,
                "individual": self.child,
                "edit_mode": False,
            },
            request=request,
        )

        self.assertIn(f"/htmx/individual/{self.child.pk}/parents/edit/", html)
        self.assertIn("Edit parents", html)

    def test_parent_dropdowns_require_change_family_permission(self):
        request = self._request(user=self.viewer)
        html = render_to_string(
            "lab/partials/family_member_row.html",
            {
                "member": self.child,
                "individual": self.child,
                "family_members": self.family.individuals.exclude(pk=self.child.pk),
                "edit_mode": True,
            },
            request=request,
        )

        self.assertNotIn('name="father_id"', html)
        self.assertNotIn('name="mother_id"', html)

        request = self._request(user=self.family_editor)
        html = render_to_string(
            "lab/partials/family_member_row.html",
            {
                "member": self.child,
                "individual": self.child,
                "family_members": self.family.individuals.exclude(pk=self.child.pk),
                "edit_mode": True,
            },
            request=request,
        )

        self.assertIn('name="father_id"', html)
        self.assertIn('name="mother_id"', html)

    def test_parent_edit_endpoints_require_change_family_permission(self):
        response = individual_parents_edit(self._request(user=self.viewer), self.child.pk)
        self.assertEqual(response.status_code, 403)

        response = individual_parents_save(
            self._request(
                method="post",
                user=self.viewer,
                data={
                    "individual_pk": self.child.pk,
                    "father_id": self.father.pk,
                    "mother_id": self.mother.pk,
                },
            ),
            self.child.pk,
        )
        self.assertEqual(response.status_code, 403)

        self.child.refresh_from_db()
        self.assertIsNone(self.child.father_id)
        self.assertIsNone(self.child.mother_id)

    def test_change_family_can_save_parent_ids_without_changing_individual_flags(self):
        response = individual_parents_save(
            self._request(
                method="post",
                user=self.family_editor,
                data={
                    "individual_pk": self.child.pk,
                    "father_id": self.father.pk,
                    "mother_id": self.mother.pk,
                },
            ),
            self.child.pk,
        )

        self.assertEqual(response.status_code, 200)
        self.child.refresh_from_db()
        self.assertEqual(self.child.father_id, self.father.pk)
        self.assertEqual(self.child.mother_id, self.mother.pk)
        self.assertTrue(self.child.is_index)
        self.assertTrue(self.child.is_affected)
