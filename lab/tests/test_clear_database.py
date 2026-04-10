from django.contrib.auth import get_user_model
from django.test import TestCase

from lab.management.commands.clear_database import Command
from lab.models import Status

User = get_user_model()


class ClearDatabaseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="regular",
            password="password",
            is_staff=True,
        )
        self.command = Command()

    def test_clear_database_preserves_defaults_and_deletes_non_superusers_without_superuser(self):
        Status.objects.create(
            name="Registered",
            description="default",
            color="gray",
            created_by=self.user,
        )
        Status.objects.create(
            name="Custom",
            description="custom",
            color="blue",
            created_by=self.user,
        )

        self.command._clear(
            {
                "include_history": False,
                "delete_genes": False,
                "delete_ontologies": False,
            }
        )

        self.assertTrue(Status.objects.filter(name="Registered").exists())
        self.assertFalse(Status.objects.filter(name="Custom").exists())
        self.assertIsNone(Status.objects.get(name="Registered").created_by)
        self.assertFalse(User.objects.filter(is_superuser=False).exists())
