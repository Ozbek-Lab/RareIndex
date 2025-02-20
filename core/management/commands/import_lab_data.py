import csv
from datetime import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from core.models import (
    Institution,
    Clinician,
    Family,
    Individual,
    SampleType,
    Sample,
    Test,
)

class Command(BaseCommand):
    help = 'Import lab data from TSV file'

    def add_arguments(self, parser):
        parser.add_argument('tsv_file', type=str, help='Path to the TSV file')
        parser.add_argument(
            '--default-user',
            type=str,
            default='openhands',
            help='Username to use for data import'
        )

    def handle(self, *args, **options):
        tsv_file = options['tsv_file']
        default_username = options['default_user']

        try:
            default_user = User.objects.get(username=default_username)
        except User.DoesNotExist:
            default_user = User.objects.create_user(
                username=default_username,
                email='openhands@all-hands.dev'
            )

        # Column mappings from TSV to model fields
        COLUMN_MAPPINGS = {
            'Özbek Lab. ID': 'lab_id',
            'Biyobanka ID': 'biobank_id',
            'Ad-Soyad': 'name',
            'TC Kimlik No': 'national_id',
            'Doğum Tarihi': 'date_of_birth',
            'ICD11': 'icd11_codes',
            'Geliş Tarihi/ay/gün/yıl': 'received_date',
            'Gönderen Kurum/Birim': 'referring_institution',
            'Klinisyen & İletişim Bilgileri': 'clinician_info',
            'Örnek Tipi': 'sample_type',
            'İzolasyonu yapan': 'isolated_by',
            'Örnek İzol. Değ.': 'isolation_values',
            'Çalışılan Test Adı': 'test_name',
            'Çalışılma Tarihi': 'test_date',
            'Hiz.Alım.Gön. Tarihi': 'sent_date',
            'Data Geliş tarihi': 'data_received_date',
            'Konsey Tarihi': 'council_date',
            'Takip Notları': 'follow_up_notes',
            'Genel Notlar/Sonuçlar': 'results',
            'İleri tetkik / planlanan': 'planned_tests',
            'Tamamlanan Tetkik': 'completed_tests',
        }

        def parse_date(date_str):
            if not date_str:
                return None
            try:
                # Try different date formats
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

        def get_or_create_institution(name):
            if not name:
                return None
            inst, _ = Institution.objects.get_or_create(name=name.strip())
            return inst

        def get_or_create_clinician(info, institution=None):
            if not info:
                return None
            
            # Parse clinician info
            name = info.split('/')[0].strip() if '/' in info else info.strip()
            email = ''
            phone = ''
            
            # Try to extract email and phone
            if '/' in info:
                contact = info.split('/', 1)[1]
                if '@' in contact:
                    email = contact.split('@')[0].strip() + '@' + contact.split('@')[1].split('/')[0].strip()
                if any(c.isdigit() for c in contact):
                    # Extract phone number (assuming it's the last part with numbers)
                    parts = contact.split('/')
                    for part in reversed(parts):
                        if any(c.isdigit() for c in part):
                            phone = part.strip()
                            break

            clinician, _ = Clinician.objects.get_or_create(
                name=name,
                defaults={
                    'email': email,
                    'phone': phone,
                    'institution': institution
                }
            )
            return clinician

        def get_or_create_sample_type(name):
            if not name:
                return None
            sample_type, _ = SampleType.objects.get_or_create(name=name.strip())
            return sample_type

        def extract_family_id(lab_id):
            # Extract family ID from lab_id (assuming format like RB_2023_01.1)
            parts = lab_id.split('.')
            return parts[0] if len(parts) > 1 else lab_id

        with open(tsv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            
            with transaction.atomic():
                for row in reader:
                    try:
                        # Get or create family
                        family_id = extract_family_id(row['Özbek Lab. ID'])
                        family, _ = Family.objects.get_or_create(family_id=family_id)

                        # Get or create institution and clinician
                        institution = get_or_create_institution(row['Gönderen Kurum/Birim'])
                        clinician = get_or_create_clinician(row['Klinisyen & İletişim Bilgileri'], institution)

                        # Create individual
                        individual, created = Individual.objects.get_or_create(
                            lab_id=row['Özbek Lab. ID'],
                            defaults={
                                'biobank_id': row['Biyobanka ID'],
                                'name': row['Ad-Soyad'],
                                'national_id': row['TC Kimlik No'],
                                'date_of_birth': parse_date(row['Doğum Tarihi']),
                                'icd11_codes': row['ICD11'],
                                'family': family,
                                'gender': '0',  # Default to unknown
                                'affected': '0',  # Default to unknown
                                'referring_clinician': clinician,
                                'referring_institution': institution,
                            }
                        )

                        # Create sample if sample type exists
                        sample_types = [s.strip() for s in row['Örnek Tipi'].split(',') if s.strip()]
                        for sample_type_name in sample_types:
                            sample_type = get_or_create_sample_type(sample_type_name)
                            if sample_type:
                                sample, _ = Sample.objects.get_or_create(
                                    individual=individual,
                                    sample_type=sample_type,
                                    received_date=parse_date(row['Geliş Tarihi/ay/gün/yıl']) or datetime.now().date(),
                                    defaults={
                                        'collection_date': parse_date(row['Geliş Tarihi/ay/gün/yıl']) or datetime.now().date(),
                                        'status': 'received',
                                        'isolated_by': row['İzolasyonu yapan'],
                                        'isolation_values': row['Örnek İzol. Değ.'],
                                    }
                                )

                                # Create test if test name exists
                                if row['Çalışılan Test Adı']:
                                    test, _ = Test.objects.get_or_create(
                                        name=row['Çalışılan Test Adı'],
                                        sample=sample,
                                        defaults={
                                            'test_date': parse_date(row['Çalışılma Tarihi']) or datetime.now().date(),
                                            'status': 'completed' if row['Tamamlanan Tetkik'] else 'pending',
                                            'sent_date': parse_date(row['Hiz.Alım.Gön. Tarihi']),
                                            'data_received_date': parse_date(row['Data Geliş tarihi']),
                                            'council_date': parse_date(row['Konsey Tarihi']),
                                            'follow_up_notes': row['Takip Notları'],
                                            'results': row['Genel Notlar/Sonuçlar'],
                                            'planned_tests': row['İleri tetkik / planlanan'],
                                            'completed_tests': row['Tamamlanan Tetkik'],
                                        }
                                    )

                        self.stdout.write(
                            self.style.SUCCESS(f'Successfully imported data for {row["Özbek Lab. ID"]}')
                        )

                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'Error importing row {row.get("Özbek Lab. ID", "unknown")}: {str(e)}')
                        )