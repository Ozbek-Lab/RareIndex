from django.core.management.base import BaseCommand

from lab.models import IdentifierType

PRIORITIES = {
    "RareBoost": 1,
    "Biobank": 2,
    "ERDERA": 3,
    "Mavigen": 4,
}


class Command(BaseCommand):
    help = "Set use_priority on known IdentifierType records"

    def handle(self, *args, **options):
        for name, priority in PRIORITIES.items():
            updated = IdentifierType.objects.filter(name=name).update(use_priority=priority)
            if updated:
                self.stdout.write(self.style.SUCCESS(f"  Set {name!r} → priority {priority}"))
            else:
                self.stdout.write(self.style.WARNING(f"  Not found: {name!r} (skipped)"))

        self.stdout.write(self.style.SUCCESS("Done."))
