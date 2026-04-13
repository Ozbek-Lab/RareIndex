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
    TEMPLATE_CONFIGS = {
        "sample-distribution-sunburst": {
            "target_model": "Sample",
            "notebook_filename": "sunburst.py",
            "default_col_span": 1,
            "show_download_menu": False,
        },
        "analysis-status-bar": {
            "target_model": "Analysis",
            "notebook_filename": "status_bar.py",
            "default_col_span": 1,
            "show_download_menu": False,
        },
        "hpo-term-network": {
            "target_model": "Individual",
            "notebook_filename": "hpo_network_visualization.py",
            "default_col_span": 2,
            "show_download_menu": False,
        },
    }

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
            template_config = self.TEMPLATE_CONFIGS[slug]
            PlotTemplate.objects.create(
                name=slug,
                slug=slug,
                description="",
                target_model=template_config["target_model"],
                query_config={},
                default_col_span=template_config["default_col_span"],
                show_download_menu=template_config["show_download_menu"],
                notebook_filename=template_config["notebook_filename"],
                is_published=True,
                created_by=self.user,
            )

        with patch("lab.management.commands.import_all.call_command") as mock_call_command:
            self.command._step18_ensure_plot_templates()

        mock_call_command.assert_not_called()

    def test_reseeds_plot_templates_when_span_mismatch(self):
        for slug in REQUIRED_PLOT_TEMPLATE_SLUGS:
            template_config = self.TEMPLATE_CONFIGS[slug]
            PlotTemplate.objects.create(
                name=slug,
                slug=slug,
                description="",
                target_model=template_config["target_model"],
                query_config={},
                default_col_span=1,
                show_download_menu=not self.TEMPLATE_CONFIGS[slug]["show_download_menu"],
                notebook_filename=template_config["notebook_filename"],
                is_published=True,
                created_by=self.user,
            )

        with patch("lab.management.commands.import_all.call_command") as mock_call_command:
            self.command._step18_ensure_plot_templates()

        mock_call_command.assert_called_once_with("seed_plot_templates")
