import csv
from datetime import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from lab.models import (
    Individual,
    SampleType,
    Sample,
    Test,
    Family
)

class Command(BaseCommand):
    help = 'Import lab data from TSV file'

    def add_arguments(self, parser):
        parser.add_argument('tsv_file', type=str, help='Path to the TSV file')
        parser.add_argument(
            '--default-user',
            type=str,
            default='admin',
            help='Username to use for data import'
        )

    def handle(self, *args, **options):
        tsv_file = options['tsv_file']
        default_username = options['default_user']

        try:
            default_user = User.objects.get(username=default_username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User {default_username} does not exist'))
            return

        def parse_date(date_str):
            if not date_str:
                return None
            try:
                formats = [
                    '%d.%m.%Y %H:%M:%S',
                    '%d.%m.%Y',
                    '%Y-%m-%d',
                ]
                for fmt in formats:
                    try:
                        return datetime.strptime(date_str.strip(), fmt).date()
                    except ValueError:
                        continue
                return None
            except Exception:
                return None

        def get_or_create_sample_type(name):
            if not name:
                return None
            sample_type, _ = SampleType.objects.get_or_create(
                name=name.strip(),
                defaults={'created_by': default_user}
            )
            return sample_type

        def extract_family_id(lab_id):
            # Extract family ID from lab_id (assuming format like RB_2023_01.1)
            parts = lab_id.split('.')
            if len(parts) > 1:
                return parts[0]  # Return RB_2023_01 from RB_2023_01.1
            # For non-family IDs (like Deneme_2023_01), return None
            if not any(prefix in lab_id for prefix in ['RB_', 'FB_']):
                return None
            return lab_id

        with open(tsv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            
            with transaction.atomic():
                for row in reader:
                    try:
                        # Get or create family if applicable
                        family = None
                        family_id = extract_family_id(row['Özbek Lab. ID'])
                        if family_id:
                            family, _ = Family.objects.get_or_create(
                                family_id=family_id,
                                defaults={'created_by': default_user}
                            )

                        # Create individual (formerly patient)
                        individual, created = Individual.objects.get_or_create(
                            lab_id=row['Özbek Lab. ID'],
                            defaults={
                                'biobank_id': row['Biyobanka ID'],
                                'full_name': row['Ad-Soyad'],
                                'tc_identity': row['TC Kimlik No'],
                                'birth_date': parse_date(row['Doğum Tarihi']),
                                'icd11_code': row['ICD11'],
                                'hpo_codes': row['HPO kodları'],
                                'family': family,
                                'created_by': default_user
                            }
                        )

                        # Create samples
                        if row['Örnek Tipi']:
                            for sample_type_name in row['Örnek Tipi'].split(','):
                                if not sample_type_name.strip():
                                    continue
                                    
                                sample_type = get_or_create_sample_type(sample_type_name)
                                
                                sample, _ = Sample.objects.get_or_create(
                                    individual=individual,
                                    sample_type=sample_type,
                                    receipt_date=parse_date(row['Geliş Tarihi/ay/gün/yıl']),
                                    defaults={
                                        'processing_date': parse_date(row['Çalışılma Tarihi']),
                                        'service_send_date': parse_date(row['Hiz.Alım.Gön. Tarihi']),
                                        'data_receipt_date': parse_date(row['Data Geliş tarihi']),
                                        'council_date': parse_date(row['Konsey Tarihi']),
                                        'isolation_by': row['İzolasyonu yapan'],
                                        'sample_measurements': row['Örnek gön.& OD değ.'],
                                        'created_by': default_user
                                    }
                                )

                                # Create test if test name exists
                                if row['Çalışılan Test Adı']:
                                    test, _ = Test.objects.get_or_create(
                                        name=row['Çalışılan Test Adı'],
                                        description=row['Genel Notlar/Sonuçlar'],
                                        created_by=default_user
                                    )

                        self.stdout.write(
                            self.style.SUCCESS(f'Successfully imported data for {row["Özbek Lab. ID"]}')
                        )

                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'Error importing row {row.get("Özbek Lab. ID", "unknown")}: {str(e)}')
                        )