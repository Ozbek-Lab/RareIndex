import csv
from datetime import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from lab.models import (
    Family,
    Individual,
    Sample,
    Test,
    Status,
    SampleType,
    Institution,
    TestType,
    Note,
)

class Command(BaseCommand):
    help = 'Import data from TSV file'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the TSV file')

    def _parse_date(self, date_str):
        """Parse date string in various formats"""
        if not date_str:
            return None

        formats = ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
        return None

    def _get_family_id(self, lab_id):
        """Extract family ID from lab_id"""
        if not lab_id:
            return None
        return lab_id.split('.')[0]

    def _get_or_create_user(self, full_name, default_user):
        """Get or create a user from a full name"""
        if not full_name:
            return default_user

        # Clean the name
        full_name = full_name.strip()
        if not full_name:
            return default_user

        # Create username from full name
        username = full_name.lower().replace(' ', '_')
        email = f"{username}@example.com"

        # Get or create the user
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': email,
                'first_name': full_name.split()[0] if ' ' in full_name else full_name,
                'last_name': ' '.join(full_name.split()[1:]) if ' ' in full_name else '',
            }
        )
        return user

    def _create_tests_from_text(self, text, individual, test_types, status, user):
        """Create Test objects from comma or newline separated text"""
        if not text:
            return

        # Split by either comma or newline
        test_names = [t.strip() for t in text.replace('\n', ',').split(',')]
        
        # Create a default sample if none exists
        default_sample = None

        for test_name in test_names:
            if not test_name:
                continue

            # Try to find matching test type
            test_type = None
            test_name_lower = test_name.lower()
            for existing_name, existing_type in test_types.items():
                if test_name_lower in existing_name.lower() or existing_name.lower() in test_name_lower:
                    test_type = existing_type
                    break

            if test_type:
                # Create default sample if needed
                if not default_sample:
                    default_sample = Sample.objects.create(
                        individual=individual,
                        sample_type=SampleType.objects.first(),  # Get the first sample type as default
                        status=status,
                        created_by=user,
                        isolation_by=user  # Use the same user as isolation_by for default sample
                    )

                # Create the test
                Test.objects.create(
                    sample=default_sample,
                    test_type=test_type,
                    status=status,
                    performed_by=user,
                    created_by=user
                )

    def handle(self, *args, **options):
        file_path = options['file_path']

        # Header mapping
        header_mapper = {
            'Özbek Lab. ID': 'individual__lab_id',
            "Biyobanka ID": "individual__biobank_id",
            "Ad-Soyad": "individual__full_name",
            "TC Kimlik No": "individual__tc_identity",
            "Doğum Tarihi": "individual__birth_date",
            "ICD11": "individual__icd11_code",
            "HPO kodları": "individual__hpo_codes",
            "Geliş Tarihi/ay/gün/yıl": "individual__receipt_date",
            "Gönderen Kurum/Birim": "individual__sending_institution__name",
            "Klinisyen & İletişim Bilgileri": "individual__sending_institution__contact",
            "Örnek Tipi": "sample__sample_type",
            "İzolasyonu yapan": "sample__isolated_by",
            "Örnek gön.& OD değ.": "sample__sample_measurements",
            "Çalışılan Test Adı": "test__test_type",
            "Çalışılma Tarihi": "test__performed_date",
            "Hiz.Alım.Gön. Tarihi": "test__service_send_date",
            "Data Geliş tarihi": "test__data_receipt_date",
            "Konsey Tarihi": "test__council_date",
            "Takip Notları": "individual__notes",
            "Genel Notlar/Sonuçlar": "individual__notes2",
            "İleri tetkik / planlanan": "individual__planned_tests",
            "Tamamlanan Tetkik": "individual__completed_tests"
        }
        # Get or create default user
        user = User.objects.first()
        if not user:
            self.stdout.write('Creating default superuser...')
            user = User.objects.create_superuser('admin', 'admin@example.com', 'admin')

        # Get or create statuses
        registered_status, _ = Status.objects.get_or_create(
            name='Registered',
            defaults={
                'color': 'gray',
                'created_by': user
            }
        )
        completed_status, _ = Status.objects.get_or_create(
            name='Completed',
            defaults={
                'color': 'green',
                'created_by': user
            }
        )
        in_progress_status, _ = Status.objects.get_or_create(
            name='In Progress',
            defaults={
                'color': 'blue',
                'created_by': user
            }
        )

        # First pass: Collect unique values and institution details
        unique_test_types = set()
        unique_sample_types = set()
        unique_family_ids = set()
        institution_details = {}  # Store both name and contact info

        self.stdout.write('First pass: Collecting unique values...')
        with open(file_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file, delimiter='\t')
            for row in reader:
                # Collect test types
                test_type = row.get('Çalışılan Test Adı')
                if test_type:
                    unique_test_types.add(test_type)

                # Collect sample types
                sample_type = row.get('Örnek Tipi')
                if sample_type:
                    unique_sample_types.add(sample_type)

                # Collect family IDs
                lab_id = row.get('Özbek Lab. ID')
                if lab_id:
                    family_id = self._get_family_id(lab_id)
                    if family_id:
                        unique_family_ids.add(family_id)

                # Collect institution details
                institution_name = row.get('Gönderen Kurum/Birim')
                contact_info = row.get('Klinisyen & İletişim Bilgileri')
                if institution_name:
                    if institution_name not in institution_details:
                        institution_details[institution_name] = set()
                    if contact_info:
                        institution_details[institution_name].add(contact_info)

        # Create TestTypes
        self.stdout.write('Creating TestTypes...')
        test_types = {}
        for name in unique_test_types:
            test_type, _ = TestType.objects.get_or_create(
                name=name,
                defaults={'created_by': user}
            )
            test_types[name] = test_type

        # Create SampleTypes
        self.stdout.write('Creating SampleTypes...')
        sample_types = {}
        for name in unique_sample_types:
            sample_type, _ = SampleType.objects.get_or_create(
                name=name,
                defaults={'created_by': user}
            )
            sample_types[name] = sample_type

        # Create Families
        self.stdout.write('Creating Families...')
        families = {}
        for family_id in unique_family_ids:
            family, _ = Family.objects.get_or_create(
                family_id=family_id,
                defaults={'created_by': user}
            )
            families[family_id] = family

        # Create Institutions with contact information
        self.stdout.write('Creating Institutions...')
        institutions = {}
        for name, contacts in institution_details.items():
            institution, _ = Institution.objects.get_or_create(
                name=name,
                defaults={
                    'contact': '\n'.join(contacts) if contacts else '',
                    'created_by': user
                }
            )
            # Update contact information if institution exists and has new contacts
            if not _ and contacts:
                existing_contacts = set(institution.contact.split('\n')) if institution.contact else set()
                all_contacts = existing_contacts.union(contacts)
                institution.contact = '\n'.join(all_contacts)
                institution.save()
            institutions[name] = institution

        # Second pass: Create objects
        self.stdout.write('Second pass: Creating objects...')
        with open(file_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file, delimiter='\t')
            for row in reader:
                try:
                    lab_id = row.get('Özbek Lab. ID')
                    if not lab_id:
                        continue

                    family_id = self._get_family_id(lab_id)
                    if not family_id or family_id not in families:
                        continue

                    # Get institution
                    institution_name = row.get('Gönderen Kurum/Birim')
                    institution = institutions.get(institution_name)

                    # Create Individual
                    individual, created = Individual.objects.get_or_create(
                        lab_id=lab_id,
                        defaults={
                            'family': families[family_id],
                            'biobank_id': row.get('Biyobanka ID'),
                            'full_name': row.get('Ad-Soyad'),
                            'tc_identity': row.get('TC Kimlik No'),
                            'birth_date': self._parse_date(row.get('Doğum Tarihi')),
                            'icd11_code': row.get('ICD11'),
                            'hpo_codes': row.get('HPO kodları'),
                            'sending_institution': institution,
                            'status': registered_status,
                            'created_by': user
                        }
                    )

                    # Concatenate and create notes if either exists
                    notes_text = []
                    if row.get('Takip Notları'):
                        notes_text.append(row.get('Takip Notları'))
                    if row.get('Genel Notlar/Sonuçlar'):
                        notes_text.append(row.get('Genel Notlar/Sonuçlar'))
                    
                    if notes_text:
                        Note.objects.create(
                            content='\n\n'.join(notes_text),
                            content_object=individual,
                            created_by=user
                        )

                    # Create completed tests
                    completed_tests = row.get('Tamamlanan Tetkik')
                    self._create_tests_from_text(completed_tests, individual, test_types, completed_status, user)

                    # Create planned tests
                    planned_tests = row.get('İleri tetkik / planlanan')
                    self._create_tests_from_text(planned_tests, individual, test_types, in_progress_status, user)

                    # Create Sample if sample type exists
                    sample_type_name = row.get('Örnek Tipi')
                    if sample_type_name and sample_type_name in sample_types:
                        # Get or create user for isolation_by
                        isolation_by = self._get_or_create_user(row.get('İzolasyonu yapan'), user)
                        
                        sample = Sample.objects.create(
                            individual=individual,
                            sample_type=sample_types[sample_type_name],
                            sample_measurements=row.get('Örnek gön.& OD değ.'),
                            status=registered_status,
                            isolation_by=isolation_by,
                            created_by=user
                        )

                        # Create Test if test type exists
                        test_type_name = row.get('Çalışılan Test Adı')
                        if test_type_name and test_type_name in test_types:
                            Test.objects.create(
                                sample=sample,
                                test_type=test_types[test_type_name],
                                performed_date=self._parse_date(row.get('Çalışılma Tarihi')),
                                service_send_date=self._parse_date(row.get('Hiz.Alım.Gön. Tarihi')),
                                data_receipt_date=self._parse_date(row.get('Data Geliş tarihi')),
                                status=registered_status,
                                performed_by=user,
                                created_by=user
                            )

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'Error processing row for {lab_id}: {str(e)}')
                    )
                    continue
            

        self.stdout.write(self.style.SUCCESS('Data import completed successfully')) 