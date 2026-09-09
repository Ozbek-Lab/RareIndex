from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from lab.models import TestType
from lab.report_defaults import normalize_testtype_report_payload, parse_report_text_reference


REPORT_FIELDS = (
    "positive_report_template",
    "negative_report_template",
    "default_positive_comment_text",
    "default_negative_result_text",
    "default_method_text",
    "default_total_reads_text",
    "default_coverage_20x_text",
    "default_mean_depth_text",
    "default_filtering_text",
    "default_limitations_text",
)
LEGACY_FIELDS = {
    f"{mode}_{field}_text"
    for mode in ("positive", "negative")
    for field in ("method", "filtering", "limitations")
}


class Command(BaseCommand):
    help = "Populate existing TestType report defaults from report_text_field_reference.md."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reference", type=Path,
            default=Path(settings.BASE_DIR) / "report_text_field_reference.md",
            help="Path to the UTF-8 Markdown reference file.",
        )
        parser.add_argument(
            "--test-type", action="append", dest="test_types", metavar="NAME",
            help="Only populate this test type (case-insensitive; repeat for multiple types).",
        )
        parser.add_argument(
            "--overwrite", action="store_true",
            help="Replace existing values; by default only empty fields are filled.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Show changes without saving them.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reference_path = Path(options["reference"])
        try:
            parsed = parse_report_text_reference(reference_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, RuntimeError) as exc:
            raise CommandError(f"Cannot load report defaults from {reference_path}: {exc}") from exc
        if not parsed:
            raise CommandError(f"No test type sections found in {reference_path}.")

        references = {}
        for name, payload in parsed.items():
            key = name.strip().casefold()
            if key in references:
                raise CommandError(f"Duplicate test type section: {name}.")
            unknown_fields = set(payload) - set(REPORT_FIELDS) - LEGACY_FIELDS
            if unknown_fields:
                raise CommandError(f"Unknown report fields for {name}: {', '.join(sorted(unknown_fields))}.")
            normalized = normalize_testtype_report_payload(payload)
            fields = {field: normalized[field] for field in REPORT_FIELDS if field in normalized}
            if not fields:
                raise CommandError(f"No report defaults found for {name}.")
            references[key] = (name, fields)

        selected = {name.strip().casefold() for name in options["test_types"] or []}
        unknown_types = selected - references.keys()
        if unknown_types:
            raise CommandError(f"No reference section for: {', '.join(sorted(unknown_types))}.")
        if selected:
            references = {key: value for key, value in references.items() if key in selected}

        matched = set()
        changes = []
        for test_type in TestType.objects.select_for_update().order_by("name", "pk"):
            key = test_type.name.strip().casefold()
            if key not in references:
                continue
            matched.add(key)
            updates = {}
            for field_name, value in references[key][1].items():
                current = getattr(test_type, field_name)
                if current == value or (not options["overwrite"] and current and current.strip()):
                    continue
                try:
                    TestType._meta.get_field(field_name).clean(value, test_type)
                except ValidationError as exc:
                    raise CommandError(f"Invalid {test_type.name}.{field_name}: {exc}") from exc
                updates[field_name] = value
            if updates:
                changes.append((test_type, updates))

        for key in sorted(references.keys() - matched):
            self.stdout.write(self.style.WARNING(f"Test type not found: {references[key][0]} (skipped)."))

        for test_type, updates in changes:
            if not options["dry_run"]:
                for field_name, value in updates.items():
                    setattr(test_type, field_name, value)
                test_type._change_reason = f"Report defaults loaded from {reference_path.name}"
                test_type.save(update_fields=list(updates))
            action = "Would update" if options["dry_run"] else "Updated"
            self.stdout.write(f"{action} {test_type.name} (#{test_type.pk}): {', '.join(updates)}")

        action = "Would update" if options["dry_run"] else "Updated"
        field_count = sum(len(updates) for _, updates in changes)
        self.stdout.write(self.style.SUCCESS(
            f"{action} {field_count} field(s) on {len(changes)} test type(s)."
        ))
