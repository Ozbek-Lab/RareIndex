import csv
from datetime import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
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
from ontologies.models import Term, Ontology
import os

class Command(BaseCommand):
    help = 'Import data from TSV file'

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

    def _get_or_create_user(self, name, admin_user):
        """Get or create a user based on name"""
        if not name:
            return admin_user
            
        # Try to find user by name
        user = User.objects.filter(username__icontains=name).first()
        if user:
            return user
            
        # Create new user if not found
        username = name.lower().replace(' ', '_')
        user = User.objects.create_user(
            username=username,
            email=f'{username}@example.com',
            password='changeme123',
            first_name=name.split()[0] if ' ' in name else name,
            last_name=name.split()[1] if ' ' in name else ''
        )
        return user

    def _get_or_create_institution(self, name, contact, admin_user):
        """Get or create an institution"""
        if not name:
            return None
            
        institution = Institution.objects.filter(name=name).first()
        if institution:
            return institution
            
        institution = Institution.objects.create(
            name=name,
            contact=contact,
            created_by=admin_user
        )
        return institution

    def _get_or_create_sample_type(self, name, admin_user):
        """Get or create a sample type"""
        if not name:
            return None
            
        sample_type = SampleType.objects.filter(name=name).first()
        if sample_type:
            return sample_type
            
        sample_type = SampleType.objects.create(
            name=name,
            created_by=admin_user
        )
        return sample_type

    def _get_hpo_terms(self, hpo_codes_str):
        """Get HPO terms from space-separated descriptions and codes"""
        if not hpo_codes_str:
            return []
            
        # Get the HP ontology
        hp_ontology = Ontology.objects.filter(type=1).first()  # 1 is HP in ONTOLOGY_CHOICES
        if not hp_ontology:
            self.stdout.write(self.style.WARNING('HP ontology not found'))
            return []
            
        # Split into individual terms (each term is "Description HP:code")
        terms = []
        current_term = []
        
        for word in hpo_codes_str.split():
            if word.startswith('HP:'):
                # This is a code, process the complete term
                code = word.replace('HP:', '')
                description = ' '.join(current_term)
                
                # Find the term by identifier
                term = Term.objects.filter(
                    ontology=hp_ontology,
                    identifier=code
                ).first()
                
                if term:
                    self.stdout.write(self.style.SUCCESS(f'Found HPO term: {term.label} (HP:{code})'))
                    terms.append(term)
                else:
                    self.stdout.write(self.style.WARNING(f'HPO term not found: {description} (HP:{code})'))
                    # Try to find by label as fallback
                    term = Term.objects.filter(
                        ontology=hp_ontology,
                        label__icontains=description
                    ).first()
                    if term:
                        self.stdout.write(self.style.SUCCESS(f'Found HPO term by label: {term.label} (HP:{term.identifier})'))
                        terms.append(term)
                
                # Reset for next term
                current_term = []
            else:
                # This is part of the description
                current_term.append(word)
        
        self.stdout.write(self.style.SUCCESS(f'Total HPO terms found: {len(terms)}'))
        return terms

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
                    # Get the received status
                    received_status = Status.objects.filter(
                        name='Received',
                        content_type=ContentType.objects.get(app_label='lab', model='sample')
                    ).first()
                    
                    default_sample = Sample.objects.create(
                        individual=individual,
                        sample_type=SampleType.objects.first(),  # Get the first sample type as default
                        status=received_status,
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
        admin_username = options.get('admin_username')
        
        if not admin_username:
            self.stdout.write(self.style.ERROR('Please provide admin username with --admin-username'))
            return
            
        try:
            admin_user = User.objects.get(username=admin_username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Admin user {admin_username} not found'))
            return

        # Get or create default status
        default_individual_status = Status.objects.filter(name='Registered').first()
        if not default_individual_status:
            default_individual_status = Status.objects.create(
                name='Registered',
                description='Sample is registered in the system',
                created_by=admin_user,
                content_type=ContentType.objects.get(app_label='lab', model='individual'),
            )
        
        # Get or create sample statuses
        sample_statuses = {
            'registered': Status.objects.filter(name='Registered').first(),
            'received': Status.objects.filter(name='Received').first(),
            'in_progress': Status.objects.filter(name='In Progress').first(),
            'completed': Status.objects.filter(name='Completed').first(),
        }
        
        # Create sample statuses if they don't exist
        if not sample_statuses['registered']:
            sample_statuses['registered'] = Status.objects.create(
                name='Registered',
                description='Sample is registered in the system',
                created_by=admin_user,
                content_type=ContentType.objects.get(app_label='lab', model='sample'),
            )
            
        if not sample_statuses['received']:
            sample_statuses['received'] = Status.objects.create(
                name='Received',
                description='Sample has been received in the lab',
                created_by=admin_user,
                content_type=ContentType.objects.get(app_label='lab', model='sample'),
            )
            
        if not sample_statuses['in_progress']:
            sample_statuses['in_progress'] = Status.objects.create(
                name='In Progress',
                description='Sample is currently being processed',
                created_by=admin_user,
                content_type=ContentType.objects.get(app_label='lab', model='sample'),
            )
            
        if not sample_statuses['completed']:
            sample_statuses['completed'] = Status.objects.create(
                name='Completed',
                description='Sample processing has been completed',
                created_by=admin_user,
                content_type=ContentType.objects.get(app_label='lab', model='sample'),
            )

        # Create leftovers file in the same directory as input file
        leftovers_path = os.path.join(os.path.dirname(file_path), 'import_ozbek_lab_leftovers.tsv')
        leftover_rows = []

        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            fieldnames = reader.fieldnames
            
            for row in reader:
                lab_id = row.get('Özbek Lab. ID')
                if not lab_id:
                    leftover_rows.append(row)
                    self.stdout.write(self.style.WARNING(f'Skipping row - missing lab ID'))
                    continue

                # Try to find existing individual
                try:
                    individual = Individual.objects.get(lab_id=lab_id)
                    self.stdout.write(f'Found existing individual: {lab_id}')
                except Individual.DoesNotExist:
                    leftover_rows.append(row)
                    self.stdout.write(self.style.WARNING(f'Skipping row - individual not found: {lab_id}'))
                    continue

                # Get or create institution
                institution = self._get_or_create_institution(
                    row.get('Gönderen Kurum/Birim'),
                    row.get('Klinisyen & İletişim Bilgileri'),
                    admin_user
                )

                # Update individual information
                individual.full_name = row.get('Ad-Soyad', individual.full_name)
                individual.tc_identity = row.get('TC Kimlik No', individual.tc_identity)
                individual.birth_date = self._parse_date(row.get('Doğum Tarihi')) or individual.birth_date
                individual.icd11_code = row.get('ICD11', individual.icd11_code)
                individual.sending_institution = institution if institution else individual.sending_institution
                individual.status = default_individual_status
                individual.save()
                
                # Get and link HPO terms
                hpo_terms = self._get_hpo_terms(row.get('HPO kodları'))
                if hpo_terms:
                    individual.hpo_terms.add(*hpo_terms)
                    self.stdout.write(self.style.SUCCESS(f'Added {len(hpo_terms)} HPO terms to {individual.full_name}'))
                
                self.stdout.write(self.style.SUCCESS(f'Updated individual: {individual.full_name}'))
                
                # Create samples
                sample_types = [s.strip() for s in row.get('Örnek Tipi', '').split(',')]
                for sample_type_name in sample_types:
                    if not sample_type_name:
                        continue

                    sample_type = self._get_or_create_sample_type(sample_type_name, admin_user)
                    if not sample_type:
                        continue

                    # Get or create isolation user
                    isolation_by = self._get_or_create_user(row.get('İzolasyonu yapan'), admin_user)
                    
                    # Check if sample already exists, treating "Tam Kan" and "Tam Kan/Serum" as the same
                    existing_sample = None
                    if sample_type_name in ["Tam Kan", "Tam Kan/Serum"]:
                        # Check for either type
                        existing_sample = Sample.objects.filter(
                            individual=individual,
                            sample_type__name__in=["Tam Kan", "Tam Kan/Serum"]
                        ).first()
                    else:
                        # Check for exact match
                        existing_sample = Sample.objects.filter(
                            individual=individual,
                            sample_type=sample_type
                        ).first()
                    
                    if existing_sample:
                        # Update existing sample with missing information
                        if not existing_sample.receipt_date:
                            existing_sample.receipt_date = self._parse_date(row.get('Geliş Tarihi/ay/gün/yıl'))
                            if existing_sample.receipt_date:
                                existing_sample.status = sample_statuses['received']
                        if not existing_sample.isolation_by:
                            existing_sample.isolation_by = isolation_by
                        if not existing_sample.status:
                            existing_sample.status = sample_statuses['registered']
                        existing_sample.save()
                        self.stdout.write(self.style.SUCCESS(f'Updated existing sample: {existing_sample}'))
                    else:
                        # Determine initial status based on receipt date
                        initial_status = sample_statuses['received'] if self._parse_date(row.get('Geliş Tarihi/ay/gün/yıl')) else sample_statuses['registered']
                        
                        # Create new sample
                        sample = Sample.objects.create(
                            individual=individual,
                            sample_type=sample_type,
                            status=initial_status,
                            receipt_date=self._parse_date(row.get('Geliş Tarihi/ay/gün/yıl')),
                            isolation_by=isolation_by,
                            created_by=admin_user,
                        )
                        self.stdout.write(self.style.SUCCESS(f'Created new sample: {sample}'))

        # Write leftover rows to file
        if leftover_rows:
            with open(leftovers_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
                writer.writeheader()
                writer.writerows(leftover_rows)
            self.stdout.write(self.style.WARNING(f'Saved {len(leftover_rows)} rows with missing data to {leftovers_path}'))

        self.stdout.write(self.style.SUCCESS('Data import completed successfully')) 