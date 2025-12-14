import csv
import os
from django.core.management.base import BaseCommand
from lab.models import Individual, CrossIdentifier

class Command(BaseCommand):
    help = 'Import sex estimations from a CSV file (RareBoostID, Sex)'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the CSV/TSV file')

    def handle(self, *args, **options):
        file_path = options['file_path']

        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'File not found: {file_path}'))
            return

        updated_count = 0
        skipped_count = 0
        not_found_count = 0

        # Define mapping from file values to Database choices
        # DB choices: [("male", "Male"), ("female", "Female"), ("other", "Other")]
        sex_map = {
            'male': 'male',
            'female': 'female',
            'unknown': None,
            'n/a': None
        }

        with open(file_path, 'r', encoding='utf-8') as f:
            # Detect delimiter (tab or comma)
            line = f.readline()
            f.seek(0)
            dialect = csv.Sniffer().sniff(line)
            reader = csv.reader(f, dialect)

            # Skip header if present (check if first col starts with 'RB')
            header = next(reader, None)
            if header and not header[0].startswith('RB_'):
                # Assuming first row is header like "Code,Sex"
                pass
            else:
                # First row is data, reset pointer
                f.seek(0)
                reader = csv.reader(f, dialect)

            for row in reader:
                if len(row) < 2:
                    continue

                rb_id = row[0].strip()
                sex_val = row[1].strip().lower()

                # Parse complex values like "Unknown (Baby)" -> "unknown"
                if 'unknown' in sex_val:
                    sex_val = 'unknown'
                elif 'diagnosis' in sex_val: # Handle N/A (Diagnosis)
                    sex_val = 'n/a'

                mapped_sex = sex_map.get(sex_val)

                if mapped_sex is None:
                    # Skip if we don't have a valid mapping (e.g. Unknown/Diagnosis)
                    skipped_count += 1
                    continue

                # Find individual by RareBoost ID
                # We assume the ID type name is "RareBoost" based on previous imports
                cross_id = CrossIdentifier.objects.filter(
                    id_type__name="RareBoost",
                    id_value=rb_id
                ).first()

                if cross_id:
                    individual = cross_id.individual
                    
                    # specific check: don't overwrite if already set? 
                    # For this task, we assume we want to update/fill missing.
                    if individual.sex != mapped_sex:
                        individual.sex = mapped_sex
                        individual.save()
                        updated_count += 1
                        self.stdout.write(f"Updated {rb_id}: {mapped_sex}")
                    else:
                        skipped_count += 1
                else:
                    self.stdout.write(self.style.WARNING(f"Individual not found: {rb_id}"))
                    not_found_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Import Complete. Updated: {updated_count}, Skipped/Unchanged: {skipped_count}, Not Found: {not_found_count}'
        ))
