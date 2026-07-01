from django.core.management.base import BaseCommand

from lab.models import IdentifierType
from lab.management.commands._import_helpers import identifier_type_example_for_name

PRIORITIES = {
    "RareBoost": 1,
    "Biobank": 2,
    "ERDERA": 3,
    "Mavigen": 4,
}

EXAMPLES = {
    "RareBoost": "RB_2025_01.1",
    "Biobank": "RD3.F12.1",
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

        for name, example in EXAMPLES.items():
            example = identifier_type_example_for_name(name) or example
            updated = IdentifierType.objects.filter(name=name, example="").update(example=example)
            if updated:
                self.stdout.write(self.style.SUCCESS(f"  Set {name!r} example → {example}"))

        self.stdout.write(self.style.SUCCESS("Done."))
