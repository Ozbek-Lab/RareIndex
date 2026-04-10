from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from lab.management.commands.import_all import (
    Command,
    REQUIRED_PLOT_TEMPLATE_SLUGS,
)
from lab.models import PlotTemplate

User = get_user_model()


class ImportAllPlotTemplateSeedingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="admin",
            password="password",
            is_staff=True,
        )
        self.command = Command()
        self.command.dry_run = False

    def test_seeds_plot_templates_when_missing(self):
        with patch("lab.management.commands.import_all.call_command") as mock_call_command:
            self.command._step18_ensure_plot_templates()

        mock_call_command.assert_called_once_with("seed_plot_templates")

    def test_skips_plot_template_seeding_when_present(self):
        for slug in REQUIRED_PLOT_TEMPLATE_SLUGS:
            PlotTemplate.objects.create(
                name=slug,
                slug=slug,
                description="",
                target_model="Sample" if "sunburst" in slug else "Analysis",
                query_config={},
                notebook_filename="sunburst.py" if "sunburst" in slug else "status_bar.py",
                is_published=True,
                created_by=self.user,
            )

        with patch("lab.management.commands.import_all.call_command") as mock_call_command:
            self.command._step18_ensure_plot_templates()

        mock_call_command.assert_not_called()
