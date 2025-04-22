import csv
from datetime import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from lab.models import (
    Institution,
    Individual,
    Sample,
    SampleType,
    Status
)
import os

class Command(BaseCommand):
    help = 'Import data from TSV file'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the TSV file')
        parser.add_argument('--admin-username', type=str, help='Admin username for created_by fields')

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

    def _parse_date(self, date_str):
        """Parse date string in various formats"""
        if not date_str:
            return None
            
        # Try different date formats
        formats = [
            '%m/%d/%y',
            '%m/%d/%Y',
            '%d-%m-%Y',
            '%Y-%m-%d',
            '%d/%m/%Y'
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
                
        return None

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
        default_status = Status.objects.filter(name='Registered').first()
        if not default_status:
            default_status = Status.objects.create(
                name='Registered',
                description='Sample is registered in the system',
                created_by=admin_user
            )

        # Create leftovers file in the same directory as input file
        leftovers_path = os.path.join(os.path.dirname(file_path), 'import_biobank_leftovers.tsv')
        leftover_rows = []

        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            fieldnames = reader.fieldnames
            
            for row in reader:
                biobank_id = row.get('Biyobanka ID')
                sample_types = row.get('Örnek Tipi', '')
                
                # Check for missing biobank ID
                if not biobank_id:
                    leftover_rows.append(row)
                    self.stdout.write(self.style.WARNING(f'Skipping row - missing biobank ID: {row.get("Ad-Soyad", "Unknown")}'))
                    continue
                
                # Check for missing sample types
                if not sample_types:
                    leftover_rows.append(row)
                    self.stdout.write(self.style.WARNING(f'Skipping row - missing sample types: {biobank_id}'))
                    continue
                
                # Get or create institution
                institution = self._get_or_create_institution(
                    row.get('Gönderen Kurum/Birim'),
                    row.get('Klinisyen & İletişim Bilgileri'),
                    admin_user
                )
                
                # Get or create individual
                individual, created = Individual.objects.get_or_create(
                    biobank_id=biobank_id,
                    defaults={
                        'full_name': row.get('Ad-Soyad'),
                        'sending_institution': institution if institution else None,
                        'status': default_status,
                        'created_by': admin_user
                    }
                )
                
                if created:
                    self.stdout.write(self.style.SUCCESS(f'Created individual: {individual.full_name}'))
                
                # Create samples
                sample_types = [s.strip() for s in sample_types.split(',')]
                for sample_type_name in sample_types:
                    if not sample_type_name:
                        continue

                    sample_type = self._get_or_create_sample_type(sample_type_name, admin_user)
                    if not sample_type:
                        continue

                    # Get or create isolation user
                    isolation_by = self._get_or_create_user(row.get('İzolasyonu yapan'), admin_user)
                    
                    sample = Sample.objects.create(
                        individual=individual,
                        sample_type=sample_type,
                        status=default_status,
                        receipt_date=self._parse_date(row.get('Geliş Tarihi/ay/gün/yıl')),
                        isolation_by=isolation_by,
                        created_by=admin_user
                    )
                    
                    self.stdout.write(self.style.SUCCESS(f'Created sample: {sample}'))

        # Write leftover rows to file
        if leftover_rows:
            with open(leftovers_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
                writer.writeheader()
                writer.writerows(leftover_rows)
            self.stdout.write(self.style.WARNING(f'Saved {len(leftover_rows)} rows with missing data to {leftovers_path}'))

        self.stdout.write(self.style.SUCCESS('Data import completed successfully')) 