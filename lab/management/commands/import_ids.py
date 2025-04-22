import csv
from datetime import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from lab.models import (
    Family,
    Individual,
    Institution,
    Status,
)

class Command(BaseCommand):
    help = 'Import individual IDs and related data from TSV file'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the TSV file')
        parser.add_argument('--admin-username', type=str, help='Admin username for created_by fields')

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

    def handle(self, *args, **options):
        file_path = options['file_path']
        admin_username = options.get('admin_username')
        
        if not admin_username:
            self.stdout.write(self.style.ERROR('Please provide admin username with --admin-username'))
            return
            
        try:
            admin_user = User.objects.get(username=admin_username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Admin user {admin_username} not found'))
            return

        # Create required statuses if they don't exist
        self.stdout.write('Ensuring required statuses exist...')
        required_statuses = {
            'Registered': {'description': 'Initial status for new entries', 'color': 'blue'},
            'Completed': {'description': 'Entry has been completed', 'color': 'green'},
            'In Progress': {'description': 'Entry is currently being processed', 'color': 'yellow'}
        }
        
        for status_name, status_data in required_statuses.items():
            status, created = Status.objects.get_or_create(
                name=status_name,
                defaults={
                    'description': status_data['description'],
                    'color': status_data['color'],
                    'created_by': admin_user
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created status: {status_name}'))
            else:
                self.stdout.write(f'Status already exists: {status_name}')

        # Get the registered status
        registered_status = Status.objects.get(name='Registered')

        # Create Unknown institution if it doesn't exist
        self.stdout.write('Ensuring Unknown institution exists...')
        unknown_institution, created = Institution.objects.get_or_create(
            name='Unknown',
            defaults={
                'contact': 'Unknown institution - placeholder for missing institution data',
                'created_by': admin_user
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Created Unknown institution'))
        else:
            self.stdout.write('Unknown institution already exists')

        # First pass: Collect unique values
        unique_family_ids = set()
        institution_details = {}  # Store both name and contact info

        self.stdout.write('First pass: Collecting unique values...')
        with open(file_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file, delimiter='\t')
            for row in reader:
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

        # Create Families
        self.stdout.write('Creating Families...')
        families = {}
        for family_id in unique_family_ids:
            family, _ = Family.objects.get_or_create(
                family_id=family_id,
                defaults={'created_by': admin_user}
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
                    'created_by': admin_user
                }
            )
            # Update contact information if institution exists and has new contacts
            if not _ and contacts:
                existing_contacts = set(institution.contact.split('\n')) if institution.contact else set()
                all_contacts = existing_contacts.union(contacts)
                institution.contact = '\n'.join(all_contacts)
                institution.save()
            institutions[name] = institution

        # Second pass: Create Individuals
        self.stdout.write('Second pass: Creating Individuals...')
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

                    # Get institution or use Unknown
                    institution_name = row.get('Gönderen Kurum/Birim')
                    institution = institutions.get(institution_name, unknown_institution)

                    # Create Individual
                    individual, created = Individual.objects.get_or_create(
                        lab_id=lab_id,
                        defaults={
                            'family': families[family_id],
                            'biobank_id': row.get('Biyobanka ID') or '',
                            'full_name': row.get('Ad-Soyad'),
                            'tc_identity': '',
                            'birth_date': self._parse_date(row.get('Doğum Tarihi')),
                            'icd11_code': '',
                            'sending_institution': institution,
                            'status': registered_status,
                            'created_by': admin_user,
                            'diagnosis': '',
                            'diagnosis_date': None,
                            'council_date': None
                        }
                    )

                    if created:
                        self.stdout.write(self.style.SUCCESS(f'Created individual: {lab_id}'))
                    else:
                        self.stdout.write(f'Individual already exists: {lab_id}')

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'Error processing row for {lab_id}: {str(e)}')
                    )
                    continue

        self.stdout.write(self.style.SUCCESS('Data import completed successfully'))
