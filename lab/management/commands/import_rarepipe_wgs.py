"""
Management command: import_rarepipe_wgs

Imports RarePipe WGS pipeline runs from a TSV file.

TSV columns (tab-separated, no header assumed):
  1. Samplesheet filename  – e.g. "samplesheet20250703.tsv"
                             The 8-digit YYYYMMDD after "samplesheet" becomes
                             the pipeline's performed_date.
  2. Output location       – absolute path to the pipeline output directory/file.
  3. Individual ID         – may use any mix of ".", "_", "-" as separators.
  4. Input location        – absolute path to the input file (e.g. VCF).
  5. RarePipe version      – e.g. "2.1.0".  A PipelineType named "RarePipe"
                             with this version is created automatically if it
                             does not already exist.

Usage:
    python manage.py import_rarepipe_wgs path/to/sheet.tsv \\
        --user admin \\
        --dry-run
"""

import csv
import re
from datetime import date
from pathlib import Path

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Value
from django.db.models.functions import Replace

from lab.models import CrossIdentifier, Individual, Pipeline, PipelineType, Status, Test


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_id(value: str) -> str:
    """Replace '.', '_', '-' with '.' for separator-agnostic comparison."""
    return re.sub(r"[._\-]", ".", value)


def _build_id_map() -> dict[str, Individual]:
    """
    Return a dict mapping normalized CrossIdentifier values → Individual.
    Built once per command run to avoid N+1 queries.
    """
    rows = (
        CrossIdentifier.objects
        .annotate(
            norm=Replace(
                Replace(
                    Replace(F("id_value"), Value("_"), Value(".")),
                    Value("-"), Value(".")
                ),
                Value(".."), Value(".")
            )
        )
        .select_related("individual")
        .values_list("norm", "individual_id")
    )
    individual_ids = {ind_id for _, ind_id in rows}
    individuals = {i.id: i for i in Individual.objects.filter(id__in=individual_ids)}
    mapping: dict[str, Individual] = {}
    for norm, ind_id in rows:
        if ind_id in individuals:
            mapping[norm] = individuals[ind_id]
    return mapping


def _parse_date_from_filename(filename: str) -> date:
    """
    Extract the YYYYMMDD date embedded in a samplesheet filename.
    e.g. "samplesheet20250703.tsv" → date(2025, 7, 3)
    """
    match = re.search(r"(\d{8})", filename)
    if not match:
        raise ValueError(f"Cannot find an 8-digit date in filename {filename!r}")
    raw = match.group(1)
    return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))


def _ensure_pipeline_types(
    versions: set[str],
    user: User,
    dry_run: bool,
    stdout,
    style,
) -> dict[str, PipelineType]:
    """
    For each version string, get or create a PipelineType with name='RarePipe'.
    Returns a mapping  version → PipelineType instance.
    """
    type_map: dict[str, PipelineType] = {}
    for version in sorted(versions):
        if dry_run:
            # In dry-run mode still fetch existing types so we can report them,
            # but never create new ones.
            pt = PipelineType.objects.filter(name="RarePipe", version=version).first()
            if pt:
                stdout.write(f"  PipelineType 'RarePipe v{version}' already exists (id={pt.pk})")
            else:
                stdout.write(
                    style.WARNING(
                        f"  [DRY RUN] Would create PipelineType 'RarePipe v{version}'"
                    )
                )
                # Use a sentinel so the rest of dry-run logic can continue
                pt = PipelineType(name="RarePipe", version=version)
            type_map[version] = pt
        else:
            pt, created = PipelineType.objects.get_or_create(
                name="RarePipe",
                version=version,
                defaults={"created_by": user},
            )
            if created:
                stdout.write(
                    style.SUCCESS(
                        f"  Created PipelineType 'RarePipe v{version}' (id={pt.pk})"
                    )
                )
            else:
                stdout.write(
                    f"  PipelineType 'RarePipe v{version}' already exists (id={pt.pk})"
                )
            type_map[version] = pt
    return type_map


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Import RarePipe WGS pipeline runs from a TSV samplesheet"

    def add_arguments(self, parser):
        parser.add_argument(
            "tsv_file",
            type=str,
            help="Path to the TSV samplesheet file",
        )
        parser.add_argument(
            "--user",
            required=True,
            help="Username to record as performed_by / created_by",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Parse and validate without writing anything to the database",
        )
        parser.add_argument(
            "--skip-header",
            action="store_true",
            dest="skip_header",
            help="Skip the first line of the TSV if it is a header row",
        )

    # ------------------------------------------------------------------

    def _read_rows(self, tsv_path: Path, skip_header: bool) -> list[list[str]]:
        """Read and return all non-blank rows from a TSV or ODS file."""
        suffix = tsv_path.suffix.lower()

        if suffix == ".ods":
            import pandas as pd
            df = pd.read_excel(tsv_path, engine="odf", header=0 if skip_header else None, dtype=str)
            rows = []
            for _, row in df.iterrows():
                cells = [str(c).strip() if c is not None and str(c) != "nan" else "" for c in row]
                if any(cells):
                    rows.append(cells)
            return rows

        # Default: TSV / CSV
        rows = []
        with tsv_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh, delimiter="\t")
            if skip_header:
                next(reader, None)
            for row in reader:
                if any(row):
                    rows.append([c.strip() for c in row])
        return rows

    def handle(self, *args, **options):
        tsv_path = Path(options["tsv_file"])
        if not tsv_path.exists():
            raise CommandError(f"File not found: {tsv_path}")

        dry_run: bool = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("-- DRY RUN: nothing will be saved --"))

        # --- resolve user & status up-front ----------------------------
        try:
            user = User.objects.get(username=options["user"])
        except User.DoesNotExist:
            raise CommandError(f"User {options['user']!r} does not exist")

        pipeline_ct = ContentType.objects.get_for_model(Pipeline)
        status = (
            Status.objects
            .filter(name__iexact="Completed", content_type=pipeline_ct)
            .first()
        )
        if status is None:
            raise CommandError(
                "No 'Completed' Status found for Pipeline. Create it in the admin first."
            )

        # --- first pass: read all rows, collect versions ---------------
        offset = 1 + int(options["skip_header"])
        all_rows = self._read_rows(tsv_path, options["skip_header"])

        version_errors: list[int] = []
        versions: set[str] = set()
        for i, row in enumerate(all_rows, start=offset):
            if len(row) < 5:
                version_errors.append(i)
                continue
            version = row[4]
            if version:
                versions.add(version)

        if version_errors:
            self.stderr.write(
                self.style.WARNING(
                    f"Lines with fewer than 5 columns (version missing): "
                    f"{version_errors} – these will be skipped"
                )
            )

        if not versions:
            raise CommandError("No version values found in column 5 – nothing to import")

        self.stdout.write(f"\nVersions found in TSV: {', '.join(sorted(versions))}")
        self.stdout.write("Ensuring PipelineType records exist…")
        type_map = _ensure_pipeline_types(versions, user, dry_run, self.stdout, self.style)

        # --- build individual ID lookup map ----------------------------
        id_map = _build_id_map()
        self.stdout.write(f"\nLoaded {len(id_map)} cross-identifier entries for matching.")

        # --- second pass: create pipelines -----------------------------
        created = skipped = errors = 0

        for lineno, row in enumerate(all_rows, start=offset):
            if len(row) < 5:
                errors += 1
                continue

            filename, output_loc, raw_id, input_loc, version = row[:5]

            if not version:
                self.stderr.write(
                    self.style.ERROR(f"Line {lineno}: empty version in column 5 – skipping")
                )
                errors += 1
                continue

            pipeline_type = type_map[version]

            # --- parse performed date ----------------------------------
            try:
                performed_date = _parse_date_from_filename(filename)
            except ValueError as exc:
                self.stderr.write(self.style.ERROR(f"Line {lineno}: {exc} – skipping"))
                errors += 1
                continue

            # --- match individual -------------------------------------
            normalized = _normalize_id(raw_id)
            individual = id_map.get(normalized)
            if individual is None:
                self.stderr.write(
                    self.style.WARNING(
                        f"Line {lineno}: no Individual found for ID {raw_id!r} "
                        f"(normalized: {normalized!r}) – skipping"
                    )
                )
                skipped += 1
                continue

            # --- find WGS test, fall back to WES ----------------------
            test = (
                Test.objects
                .filter(
                    sample__individual=individual,
                    test_type__name__icontains="WGS",
                )
                .order_by("id")
                .first()
            )

            if test is None:
                self.stderr.write(
                    self.style.WARNING(
                        f"Line {lineno}: {individual} has no WGS test – trying WES"
                    )
                )
                test = (
                    Test.objects
                    .filter(
                        sample__individual=individual,
                        test_type__name__icontains="WES",
                    )
                    .order_by("id")
                    .first()
                )

            if test is None:
                self.stderr.write(
                    self.style.ERROR(
                        f"Line {lineno}: {individual} has no WGS or WES test – skipping"
                    )
                )
                skipped += 1
                continue

            # --- duplicate guard --------------------------------------
            if Pipeline.objects.filter(
                test=test,
                type=pipeline_type,
                performed_date=performed_date,
                output_location=output_loc,
            ).exists():
                self.stdout.write(
                    f"Line {lineno}: Pipeline already exists for "
                    f"{individual} / {performed_date} / RarePipe v{version} – skipping"
                )
                skipped += 1
                continue

            self.stdout.write(
                f"Line {lineno}: "
                f"{'[DRY RUN] ' if dry_run else ''}"
                f"Creating Pipeline for {individual} "
                f"on {performed_date} – RarePipe v{version} (test #{test.pk})"
            )

            if not dry_run:
                Pipeline.objects.create(
                    test=test,
                    performed_date=performed_date,
                    performed_by=user,
                    type=pipeline_type,
                    status=status,
                    input_location=input_loc,
                    output_location=output_loc,
                    created_by=user,
                )

            created += 1

        # --- summary --------------------------------------------------
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Done.  "
            f"{'Would create' if dry_run else 'Created'}: {created}  |  "
            f"Skipped: {skipped}  |  "
            f"Errors: {errors}"
        ))
