from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.test import TestCase

from lab.management.commands.import_all import Command
from lab.models import Contact

User = get_user_model()


class ImportAllAdminUserTests(TestCase):
    def setUp(self):
        self.command = Command()
        self.command.dry_run = False

    def test_creates_superuser_when_missing(self):
        admin_user = self.command._resolve_admin_user("admin")

        admin_user.refresh_from_db()
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        self.assertEqual(admin_user.username, "admin")

    def test_promotes_existing_user_to_admin(self):
        user = User.objects.create_user(username="admin", password="password")

        admin_user = self.command._resolve_admin_user("admin")

        user.refresh_from_db()
        self.assertEqual(admin_user.pk, user.pk)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_dry_run_rejects_missing_admin_user(self):
        self.command.dry_run = True

        with self.assertRaises(CommandError):
            self.command._resolve_admin_user("admin")

    def test_parses_multiple_analysis_performers_from_comma_separated_column(self):
        self.command.admin_user = User.objects.create_superuser(
            username="admin",
            password="password",
        )
        performers = self.command._parse_analysis_performers(
            "Ayça Yiğit, Mert Pekerbaş, Ravza Nur Yıldırım"
        )

        self.assertEqual([u.username for u in performers], [
            "ayça_yiğit",
            "mert_pekerbaş",
            "ravza_nur_yıldırım",
        ])
        contact = Contact.objects.get(full_name="Ayça Yiğit")
        self.assertEqual(contact.user.username, "ayça_yiğit")

    def test_builds_clinician_assignments_with_overflow_to_last_user(self):
        self.command.stdout = StringIO()
        self.command.issue_records = []
        assignments = self.command._build_clinician_assignments(
            "Ayça Yiğit, Mert Pekerbaş, Ravza Nur Yıldırım",
            " ayca@example.com , 0532 111 22 33 ",
            "mert@example.com, 0533 444 55 66, extra@example.com",
        )

        self.assertEqual(assignments, [
            ("Ayça Yiğit", ["ayca@example.com"]),
            ("Mert Pekerbaş", ["05321112233"]),
            ("Ravza Nur Yıldırım", ["mert@example.com", "05334445566", "extra@example.com"]),
        ])
        self.assertIn("INFO: Clinician contact edge case:", self.command.stdout.getvalue())
        self.assertEqual(self.command.issue_records[-1]["severity"], "info")

    def test_applies_contact_details_to_contact_and_user_email(self):
        user = User.objects.create_user(username="ayca_yigit", password="password")
        contact = Contact.objects.create(full_name="Ayça Yiğit", user=user, created_by=user)

        self.command._apply_contact_details(
            contact,
            ["ayca@example.com", "05321112233"],
        )

        user.refresh_from_db()
        contact.refresh_from_db()
        self.assertEqual(user.email, "ayca@example.com")
        self.assertEqual(contact.emails, ["ayca@example.com"])
        self.assertEqual(contact.phones, ["05321112233"])
