from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from lab.models import PlotTemplate

class Command(BaseCommand):
    help = 'Seeds the database with default PlotTemplates for the published Marimo notebooks.'

    def handle(self, *args, **options):
        # Ensure we have a staff user to own these
        admin_user = User.objects.filter(is_staff=True).first()
        if not admin_user:
            self.stdout.write(self.style.ERROR('No staff user found to own templates. Please create one or run with --user.'))
            return

        templates = [
            {
                "name": "Sample Distribution Sunburst",
                "slug": "sample-distribution-sunburst",
                "description": "Interactive hierarchy of samples by type and status.",
                "target_model": "Sample",
                "default_col_span": 1,
                "show_download_menu": False,
                "notebook_filename": "sunburst.py",
                "query_config": {
                    "values": ["sample_type__name", "statuses__name"],
                    "annotate": {"count": {"count": "id"}}
                },
                "is_published": True
            },
            {
                "name": "Analysis Status Bar Chart",
                "slug": "analysis-status-bar",
                "description": "Bar chart showing current progress of all analysis records.",
                "target_model": "Analysis",
                "default_col_span": 1,
                "show_download_menu": False,
                "notebook_filename": "status_bar.py",
                "query_config": {
                    "values": ["statuses__name"],
                    "annotate": {"count": {"count": "id"}}
                },
                "is_published": True
            },
            {
                "name": "HPO Term Network",
                "slug": "hpo-term-network",
                "description": "Network visualization of HPO terms used across individuals.",
                "target_model": "Individual",
                "default_col_span": 2,
                "show_download_menu": False,
                "notebook_filename": "hpo_network_visualization.py",
                "query_config": {
                    "values": ["hpo_terms__identifier"],
                    "annotate": {"count": {"count": "id"}}
                },
                "is_published": True
            }
        ]

        for t_data in templates:
            slug = t_data.pop("slug")
            obj, created = PlotTemplate.objects.update_or_create(
                slug=slug,
                defaults={**t_data, "created_by": admin_user}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created template: {obj.name}'))
            else:
                self.stdout.write(self.style.NOTICE(f'Updated template: {obj.name}'))

        self.stdout.write(self.style.SUCCESS('Successfully seeded plot templates.'))
