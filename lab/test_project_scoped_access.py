from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from lab.access import (
    accessible_individuals,
    accessible_projects,
    user_can_change_object,
    user_can_manage_project,
)
from lab.management.commands.create_groups import expected_permission_codenames
from lab.management.commands.import_all import Command as ImportAllCommand

from .models import CrossIdentifier, IdentifierType, Individual, Project, ProjectMembership


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class ProjectScopedAccessTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(username="project-member", password="password")
        self.editor = User.objects.create_user(username="project-editor", password="password")
        self.mixed_member = User.objects.create_user(username="mixed-member", password="password")
        self.outsider = User.objects.create_user(username="outsider", password="password")
        self.staff = User.objects.create_user(
            username="staff-user",
            password="password",
            is_staff=True,
        )
        self.superuser = User.objects.create_superuser(username="root", password="password")

        self.visible_project = Project.objects.create(name="Visible Project", created_by=self.staff)
        self.manager_project = Project.objects.create(name="Manager Project", created_by=self.staff)
        self.viewer_project = Project.objects.create(name="Viewer Project", created_by=self.staff)
        self.hidden_project = Project.objects.create(name="Hidden Project", created_by=self.staff)
        self.visible_individual = Individual.objects.create(full_name="Visible Person", created_by=self.staff)
        self.hidden_individual = Individual.objects.create(full_name="Hidden Person", created_by=self.staff)
        self.visible_project.individuals.add(self.visible_individual)
        self.manager_project.individuals.add(self.visible_individual)
        self.viewer_project.individuals.add(self.visible_individual)
        self.hidden_project.individuals.add(self.hidden_individual)
        view_individual_perm = Permission.objects.get(
            content_type=ContentType.objects.get_for_model(Individual),
            codename="view_individual",
        )
        change_individual_perm = Permission.objects.get(
            content_type=ContentType.objects.get_for_model(Individual),
            codename="change_individual",
        )
        view_project_perm = Permission.objects.get(
            content_type=ContentType.objects.get_for_model(Project),
            codename="view_project",
        )
        change_project_perm = Permission.objects.get(
            content_type=ContentType.objects.get_for_model(Project),
            codename="change_project",
        )
        self.member.user_permissions.add(
            view_individual_perm,
            view_project_perm,
        )
        self.editor.user_permissions.add(
            view_individual_perm,
            change_individual_perm,
            view_project_perm,
        )
        self.mixed_member.user_permissions.add(
            view_individual_perm,
            change_individual_perm,
            view_project_perm,
            change_project_perm,
        )
        self.outsider.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Individual),
                codename="view_individual",
            ),
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Project),
                codename="view_project",
            ),
        )
        ProjectMembership.objects.create(
            project=self.visible_project,
            user=self.member,
            role=ProjectMembership.Role.VIEWER,
            created_by=self.staff,
        )
        ProjectMembership.objects.create(
            project=self.visible_project,
            user=self.editor,
            role=ProjectMembership.Role.EDITOR,
            created_by=self.staff,
        )
        ProjectMembership.objects.create(
            project=self.visible_project,
            user=self.mixed_member,
            role=ProjectMembership.Role.VIEWER,
            created_by=self.staff,
        )
        ProjectMembership.objects.create(
            project=self.viewer_project,
            user=self.mixed_member,
            role=ProjectMembership.Role.VIEWER,
            created_by=self.staff,
        )
        ProjectMembership.objects.create(
            project=self.manager_project,
            user=self.mixed_member,
            role=ProjectMembership.Role.MANAGER,
            created_by=self.staff,
        )

        identifier_type = IdentifierType.objects.create(
            name="Primary",
            use_priority=1,
            created_by=self.staff,
        )
        CrossIdentifier.objects.create(
            individual=self.visible_individual,
            id_type=identifier_type,
            id_value="VISIBLE-1",
            created_by=self.staff,
        )
        CrossIdentifier.objects.create(
            individual=self.hidden_individual,
            id_type=identifier_type,
            id_value="HIDDEN-1",
            created_by=self.staff,
        )

    def test_project_membership_model_contract(self):
        membership = ProjectMembership.objects.get(
            project=self.visible_project,
            user=self.member,
        )

        self.assertEqual(membership.role, ProjectMembership.Role.VIEWER)
        self.assertIn(("manager", "Manager"), ProjectMembership.Role.choices)
        self.assertEqual(
            str(membership),
            "project-member in Visible Project (Viewer)",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProjectMembership.objects.create(
                    project=self.visible_project,
                    user=self.member,
                    role=ProjectMembership.Role.EDITOR,
                    created_by=self.staff,
                )

    def test_nonstaff_access_is_scoped_to_project_memberships(self):
        self.assertEqual(
            set(accessible_projects(self.member).values_list("pk", flat=True)),
            {self.visible_project.pk},
        )
        self.assertEqual(
            set(accessible_individuals(self.member).values_list("pk", flat=True)),
            {self.visible_individual.pk},
        )
        self.assertFalse(accessible_projects(self.outsider).exists())
        self.assertFalse(accessible_individuals(self.outsider).exists())

        self.client.force_login(self.member)
        response = self.client.get(reverse("lab:individual_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "VISIBLE-1")
        self.assertNotContains(response, "HIDDEN-1")

        response = self.client.get(reverse("lab:project_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visible Project")
        self.assertNotContains(response, "Hidden Project")

        self.assertEqual(
            self.client.get(
                reverse("lab:individual_detail", args=[self.hidden_individual.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("lab:project_detail", args=[self.hidden_project.pk])
            ).status_code,
            404,
        )

    def test_staff_and_superusers_bypass_project_scoping(self):
        for user in (self.staff, self.superuser):
            self.client.force_login(user)
            self.assertEqual(
                self.client.get(
                    reverse("lab:individual_detail", args=[self.hidden_individual.pk])
                ).status_code,
                200,
            )
            self.assertEqual(
                self.client.get(
                    reverse("lab:project_detail", args=[self.hidden_project.pk])
                ).status_code,
                200,
            )

    def test_viewer_role_cannot_change_individual_even_with_model_permission(self):
        self.member.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Individual),
                codename="change_individual",
            )
        )

        self.assertFalse(
            user_can_change_object(
                self.member,
                self.visible_individual,
                "lab.change_individual",
            )
        )

        self.client.force_login(self.member)
        response = self.client.get(
            reverse("lab:individual_demographics_edit", args=[self.visible_individual.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_editor_role_can_change_individual_with_model_permission(self):
        self.assertTrue(
            user_can_change_object(
                self.editor,
                self.visible_individual,
                "lab.change_individual",
            )
        )

        self.client.force_login(self.editor)
        response = self.client.get(
            reverse("lab:individual_demographics_edit", args=[self.visible_individual.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_strongest_project_role_wins_for_individual_access(self):
        self.assertTrue(
            user_can_change_object(
                self.mixed_member,
                self.visible_individual,
                "lab.change_individual",
            )
        )
        self.assertTrue(
            user_can_manage_project(
                self.mixed_member,
                self.manager_project,
                "lab.change_project",
            )
        )
        self.assertFalse(
            user_can_manage_project(
                self.mixed_member,
                self.viewer_project,
                "lab.change_project",
            )
        )


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class ProjectMembershipManagementUITests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="membership-staff",
            password="password",
            is_staff=True,
        )
        self.superuser = User.objects.create_superuser(
            username="membership-root",
            password="password",
        )
        self.member = User.objects.create_user(username="membership-member", password="password")
        self.target_user = User.objects.create_user(username="target-user", password="password")
        self.second_target_user = User.objects.create_user(username="second-target", password="password")
        self.project = Project.objects.create(name="Membership Project", created_by=self.staff)
        self.member.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Project),
                codename="view_project",
            )
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.member,
            role=ProjectMembership.Role.VIEWER,
            created_by=self.staff,
        )

    def test_project_members_tab_is_staff_only(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("lab:project_detail", args=[self.project.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "project-members-panel")
        self.assertNotContains(
            response,
            reverse("lab:project_membership_add", args=[self.project.pk]),
        )

        for user in (self.staff, self.superuser):
            self.client.force_login(user)
            response = self.client.get(reverse("lab:project_detail", args=[self.project.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "project-members-panel")
            self.assertContains(
                response,
                reverse("lab:project_membership_add", args=[self.project.pk]),
            )

    def test_project_membership_crud_from_project_page_is_staff_only(self):
        add_url = reverse("lab:project_membership_add", args=[self.project.pk])

        self.client.force_login(self.member)
        response = self.client.post(
            add_url,
            {"user": self.target_user.pk, "role": ProjectMembership.Role.EDITOR},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            ProjectMembership.objects.filter(
                project=self.project,
                user=self.target_user,
            ).exists()
        )

        self.client.force_login(self.staff)
        response = self.client.post(
            add_url,
            {"user": self.target_user.pk, "role": ProjectMembership.Role.EDITOR},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        membership = ProjectMembership.objects.get(
            project=self.project,
            user=self.target_user,
        )
        self.assertEqual(membership.role, ProjectMembership.Role.EDITOR)
        self.assertEqual(membership.created_by, self.staff)

        response = self.client.post(
            reverse(
                "lab:project_membership_update",
                args=[self.project.pk, membership.pk],
            ),
            {"role": ProjectMembership.Role.MANAGER},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        membership.refresh_from_db()
        self.assertEqual(membership.role, ProjectMembership.Role.MANAGER)

        response = self.client.delete(
            reverse(
                "lab:project_membership_remove",
                args=[self.project.pk, membership.pk],
            ),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProjectMembership.objects.filter(pk=membership.pk).exists())

    def test_project_membership_add_from_project_page_accepts_multiple_users(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("lab:project_membership_add", args=[self.project.pk]),
            {
                "user": [self.target_user.pk, self.second_target_user.pk],
                "role": ProjectMembership.Role.EDITOR,
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        created_pairs = set(
            ProjectMembership.objects.filter(
                project=self.project,
                user__in=[self.target_user, self.second_target_user],
            ).values_list("user__username", "role")
        )
        self.assertEqual(
            created_pairs,
            {
                ("target-user", ProjectMembership.Role.EDITOR),
                ("second-target", ProjectMembership.Role.EDITOR),
            },
        )


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class ProjectMembershipConfigurationTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="config-staff",
            password="password",
            is_staff=True,
        )
        self.view_user = User.objects.create_user(username="config-viewer", password="password")
        self.manager = User.objects.create_user(username="config-manager", password="password")
        self.target_user = User.objects.create_user(username="config-target", password="password")
        self.second_target_user = User.objects.create_user(username="config-second-target", password="password")
        self.project = Project.objects.create(name="Config Project", created_by=self.staff)
        self.second_project = Project.objects.create(name="Second Config Project", created_by=self.staff)
        self.third_project = Project.objects.create(name="Third Config Project", created_by=self.staff)
        self.existing_membership = ProjectMembership.objects.create(
            project=self.project,
            user=self.view_user,
            role=ProjectMembership.Role.VIEWER,
            created_by=self.staff,
        )
        for project in (self.project, self.second_project, self.third_project):
            ProjectMembership.objects.create(
                project=project,
                user=self.manager,
                role=ProjectMembership.Role.MANAGER,
                created_by=self.staff,
            )
        self.content_type = ContentType.objects.get_for_model(ProjectMembership)

    def _permission(self, codename):
        return Permission.objects.get(
            content_type=self.content_type,
            codename=codename,
        )

    def test_configuration_section_respects_project_membership_crud_permissions(self):
        self.view_user.user_permissions.add(self._permission("view_projectmembership"))
        self.client.force_login(self.view_user)

        response = self.client.get(reverse("lab:configurations"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Project Memberships")
        self.assertContains(response, "Config Project")
        self.assertNotContains(
            response,
            reverse("lab:config_form_add", args=["projectmembership"]),
        )
        self.assertEqual(
            self.client.get(
                reverse("lab:config_form_add", args=["projectmembership"])
            ).status_code,
            403,
        )

        self.manager.user_permissions.add(
            self._permission("view_projectmembership"),
            self._permission("add_projectmembership"),
            self._permission("change_projectmembership"),
            self._permission("delete_projectmembership"),
        )
        self.client.force_login(self.manager)
        response = self.client.get(reverse("lab:configurations"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("lab:config_form_add", args=["projectmembership"]),
        )
        self.assertContains(
            response,
            reverse(
                "lab:config_form_edit",
                args=["projectmembership", self.existing_membership.pk],
            ),
        )
        self.assertContains(
            response,
            reverse(
                "lab:config_delete_confirm",
                args=["projectmembership", self.existing_membership.pk],
            ),
        )

    def test_project_membership_crud_from_configurations_page(self):
        self.manager.user_permissions.add(
            self._permission("view_projectmembership"),
            self._permission("add_projectmembership"),
            self._permission("change_projectmembership"),
            self._permission("delete_projectmembership"),
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("lab:config_form_add", args=["projectmembership"]),
            {
                "project": self.project.pk,
                "user": self.target_user.pk,
                "role": ProjectMembership.Role.EDITOR,
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        membership = ProjectMembership.objects.get(
            project=self.project,
            user=self.target_user,
        )
        self.assertEqual(membership.created_by, self.manager)

        response = self.client.post(
            reverse("lab:config_form_edit", args=["projectmembership", membership.pk]),
            {
                "project": self.project.pk,
                "user": self.target_user.pk,
                "role": ProjectMembership.Role.MANAGER,
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        membership.refresh_from_db()
        self.assertEqual(membership.role, ProjectMembership.Role.MANAGER)

        response = self.client.post(
            reverse("lab:config_delete", args=["projectmembership", membership.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProjectMembership.objects.filter(pk=membership.pk).exists())

    def test_project_membership_config_add_creates_all_project_user_combinations(self):
        self.manager.user_permissions.add(
            self._permission("view_projectmembership"),
            self._permission("add_projectmembership"),
            self._permission("change_projectmembership"),
            self._permission("delete_projectmembership"),
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("lab:config_form_add", args=["projectmembership"]),
            {
                "project": [
                    self.project.pk,
                    self.second_project.pk,
                    self.third_project.pk,
                ],
                "user": [
                    self.target_user.pk,
                    self.second_target_user.pk,
                ],
                "role": ProjectMembership.Role.EDITOR,
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        created_pairs = set(
            ProjectMembership.objects.filter(
                project__in=[self.project, self.second_project, self.third_project],
                user__in=[self.target_user, self.second_target_user],
            ).values_list("project__name", "user__username", "role", "created_by")
        )
        self.assertEqual(
            created_pairs,
            {
                ("Config Project", "config-target", ProjectMembership.Role.EDITOR, self.manager.pk),
                ("Config Project", "config-second-target", ProjectMembership.Role.EDITOR, self.manager.pk),
                ("Second Config Project", "config-target", ProjectMembership.Role.EDITOR, self.manager.pk),
                ("Second Config Project", "config-second-target", ProjectMembership.Role.EDITOR, self.manager.pk),
                ("Third Config Project", "config-target", ProjectMembership.Role.EDITOR, self.manager.pk),
                ("Third Config Project", "config-second-target", ProjectMembership.Role.EDITOR, self.manager.pk),
            },
        )

    def test_project_membership_config_add_updates_existing_combination_role(self):
        self.manager.user_permissions.add(
            self._permission("view_projectmembership"),
            self._permission("add_projectmembership"),
            self._permission("change_projectmembership"),
            self._permission("delete_projectmembership"),
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("lab:config_form_add", args=["projectmembership"]),
            {
                "project": [self.project.pk],
                "user": [self.view_user.pk, self.target_user.pk],
                "role": ProjectMembership.Role.MANAGER,
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.existing_membership.refresh_from_db()
        self.assertEqual(self.existing_membership.role, ProjectMembership.Role.MANAGER)
        self.assertTrue(
            ProjectMembership.objects.filter(
                project=self.project,
                user=self.target_user,
                role=ProjectMembership.Role.MANAGER,
                created_by=self.manager,
            ).exists()
        )


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class ProjectMembershipScriptAndAdminTests(TestCase):
    def test_project_membership_is_registered_in_admin_surfaces(self):
        self.assertIn(ProjectMembership, admin.site._registry)
        self.assertTrue(
            any(inline.model is ProjectMembership for inline in admin.site._registry[Project].inlines)
        )
        self.assertTrue(
            any(inline.model is ProjectMembership for inline in admin.site._registry[User].inlines)
        )

    def test_create_groups_includes_project_membership_permissions(self):
        call_command("create_groups")

        type_manager_codenames = set(
            Group.objects.get(name="Type Manager").permissions.values_list(
                "codename",
                flat=True,
            )
        )
        basic_user_codenames = set(
            Group.objects.get(name="Basic User").permissions.values_list(
                "codename",
                flat=True,
            )
        )

        self.assertTrue(
            {
                "add_projectmembership",
                "change_projectmembership",
                "delete_projectmembership",
                "view_projectmembership",
            }.issubset(type_manager_codenames)
        )
        self.assertIn("view_projectmembership", basic_user_codenames)
        self.assertIn("view_historicalprojectmembership", basic_user_codenames)
        self.assertIn(
            "view_historicalprojectmembership",
            expected_permission_codenames()["lab"],
        )

    def test_import_all_ensures_groups_before_using_imported_permissions(self):
        with patch("lab.management.commands.import_all.call_command") as mocked_call:
            with self.assertRaises(CommandError):
                ImportAllCommand().handle(
                    xlsx_file="/tmp/rareindex-missing-import.xlsx",
                    admin_username="import-admin",
                    rarepipe_tsv=None,
                    yayin_ici=None,
                    forms_dir=None,
                    reports_dir=None,
                    skip_hgnc=True,
                    dry_run=False,
                )

        mocked_call.assert_called_once_with("create_groups")
