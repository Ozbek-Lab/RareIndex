from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from lab.models import Status


class Command(BaseCommand):
    help = "Backfill Font Awesome 7 icon classes on existing Status records"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only print changes without saving to the database",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)

        # Resolve content types once
        ct_individual = ContentType.objects.get(app_label="lab", model="individual")
        ct_sample = ContentType.objects.get(app_label="lab", model="sample")
        ct_test = ContentType.objects.get(app_label="lab", model="test")
        ct_analysis = ContentType.objects.get(app_label="lab", model="analysis")
        ct_project = ContentType.objects.get(app_label="lab", model="project")
        ct_task = ContentType.objects.get(app_label="lab", model="task")

        # Map of (name, content_type) -> FA7 icon class
        icon_map = {
            # Individuals
            ("Registered", ct_individual): "fa-user-plus",
            ("Family", ct_individual): "fa-people-group",
            ("Solved Family", ct_individual): "fa-people-group",
            ("Solved", ct_individual): "fa-circle-check",

            # Samples
            ("Not Available", ct_sample): "fa-ban",
            ("Pending Blood Recovery", ct_sample): "fa-droplet",
            ("Pending Isolation", ct_sample): "fa-vials",
            ("Available", ct_sample): "fa-circle-check",

            # Projects
            ("In Progress", ct_project): "fa-diagram-project",
            ("Setting Up", ct_project): "fa-gears",
            ("Completed", ct_project): "fa-flag-checkered",

            # Analyses
            ("Completed", ct_analysis): "fa-circle-check",
            ("In Progress", ct_analysis): "fa-spinner",
            ("Pending Data", ct_analysis): "fa-hourglass-half",

            # Tests
            ("Completed", ct_test): "fa-circle-check",
            ("In Progress", ct_test): "fa-spinner",
            ("Pending", ct_test): "fa-clock",

            # Tasks
            ("Ongoing", ct_task): "fa-list-check",
            ("Completed", ct_task): "fa-circle-check",
            ("Overdue", ct_task): "fa-triangle-exclamation",
        }

        updated = 0
        missing = []

        for (name, ct), icon in icon_map.items():
            status = Status.objects.filter(name=name, content_type=ct).first()
            if not status:
                missing.append((name, ct.model))
                continue
            if status.icon != icon:
                self.stdout.write(
                    f"Updating icon for '{name}' ({ct.app_label}|{ct.model}): '{status.icon}' -> '{icon}'"
                )
                if not dry_run:
                    status.icon = icon
                    status.save(update_fields=["icon"]) 
                updated += 1

        if updated:
            if dry_run:
                self.stdout.write(self.style.WARNING(f"[DRY-RUN] Would update {updated} statuses."))
            else:
                self.stdout.write(self.style.SUCCESS(f"Updated {updated} statuses."))
        else:
            self.stdout.write("No status icons needed updating.")

        if missing:
            self.stdout.write(self.style.WARNING("Statuses not found (skipped):"))
            for name, model in missing:
                self.stdout.write(f" - {name} | {model}")

        self.stdout.write(self.style.SUCCESS("Backfill complete."))