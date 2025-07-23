from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from lab.models import (
    Individual, Test, TestType, Analysis, AnalysisType,
    Status, Sample, SampleType, Institution
)
import csv
from datetime import datetime
import os

User = get_user_model()

class Command(BaseCommand):
    help = 'Import analysis tracking data from TSV file'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the TSV file')
        parser.add_argument(
            '--admin-user',
            type=str,
            help='Username of the admin user to use for created_by fields',
            required=True
        )

    def _parse_date(self, date_str):
        if not date_str or date_str.lower() == 'na':
            return None
        try:
            return datetime.strptime(date_str, '%d.%m.%Y').date()
        except ValueError:
            return None

    def _get_or_create_user(self, name, admin_user):
        if not name:
            return None
        try:
            return User.objects.get(username=name)
        except User.DoesNotExist:
            return admin_user

    def _get_or_create_status(self, name, description, color, admin_user, content_type=None):
        if not name:
            return None
        status, created = Status.objects.get_or_create(
            name=name,
            content_type=content_type,
            defaults={
                'description': description or '',
                'color': color or '#000000',
                'created_by': admin_user,
            }
        )
        return status

    def _get_or_create_test_type(self, name, admin_user):
        if not name:
            return None
        test_type, created = TestType.objects.get_or_create(
            name=name,
            defaults={'created_by': admin_user}
        )
        return test_type

    def _get_or_create_sample_type(self, name, admin_user):
        if not name:
            return None
        sample_type, created = SampleType.objects.get_or_create(
            name=name,
            defaults={'created_by': admin_user}
        )
        return sample_type

    def _get_or_create_analysis_type(self, name, description, admin_user):
        if not name:
            return None
        analysis_type, created = AnalysisType.objects.get_or_create(
            name=name,
            defaults={
                'description': description or '',
                'created_by': admin_user
            }
        )
        return analysis_type

    def _get_or_create_placeholder_sample(self, individual, admin_user):
        # Create a placeholder sample type if it doesn't exist
        placeholder_type = self._get_or_create_sample_type('Placeholder', admin_user)
        
        # Create a placeholder sample
        sample = Sample.objects.create(
            individual=individual,
            sample_type=placeholder_type,
            status=Status.objects.get(name='Registered'),
            isolation_by=admin_user,
            created_by=admin_user
        )
        return sample

    def handle(self, *args, **options):
        file_path = options['file_path']
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'File not found: {file_path}'))
            return

        # Get admin user for created_by fields
        try:
            admin_user = User.objects.get(username=options['admin_user'])
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Admin user not found: {options["admin_user"]}'))
            return

        # Get or create required statuses
        completed_status = self._get_or_create_status(
            'Completed',
            'Analysis completed',
            '#00FF00',
            admin_user,
            ContentType.objects.get_for_model(Analysis)
        )

        # Get or create Gennext analysis type
        gennext_type = self._get_or_create_analysis_type(
            'Gennext',
            '',
            admin_user
        )

        # Track unique test types
        test_types = {}

        # Track rows with missing lab IDs
        leftover_rows = []

        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                lab_id = row.get('Özbek Lab. ID')
                if not lab_id:
                    leftover_rows.append(row)
                    self.stdout.write(self.style.WARNING(f'Skipping row with missing lab ID'))
                    continue

                try:
                    individual = Individual.objects.get(cross_ids__id_value=lab_id)
                except Individual.DoesNotExist:
                    leftover_rows.append(row)
                    self.stdout.write(self.style.WARNING(f'Individual not found with lab_id: {lab_id}'))
                    continue

                # Get or create test type
                veri_kaynagi = row.get('VERİ KAYNAĞI')
                if not veri_kaynagi:
                    leftover_rows.append(row)
                    self.stdout.write(self.style.WARNING(f'Skipping row with missing VERİ KAYNAĞI for lab_id: {lab_id}'))
                    continue

                test_type = self._get_or_create_test_type(veri_kaynagi, admin_user)
                if not test_type:
                    leftover_rows.append(row)
                    self.stdout.write(self.style.WARNING(f'Skipping row with invalid test type for lab_id: {lab_id}'))
                    continue

                test_types[veri_kaynagi] = test_type

                # Create default status for analysis
                status = self._get_or_create_status(
                    'In Progress',
                    'Analysis is in progress',
                    '#0000FF',
                    admin_user,
                    ContentType.objects.get_for_model(Analysis)
                )

                # Get first sample or create placeholder
                sample = individual.samples.first()
                if not sample:
                    sample = self._get_or_create_placeholder_sample(individual, admin_user)

                # Create test
                test = Test.objects.create(
                    test_type=test_type,
                    status=completed_status,
                    data_receipt_date=self._parse_date(row.get('Data Geliş Tarihi')),
                    sample=sample,
                    created_by=admin_user
                )

                # Create analysis if data upload date exists
                data_upload_date = self._parse_date(row.get('Data yüklenme tarihi/emre'))
                if data_upload_date:
                    analysis = Analysis.objects.create(
                        type=gennext_type,
                        status=status,
                        performed_date=data_upload_date,
                        performed_by=admin_user,
                        test=test,
                        created_by=admin_user
                    )

        # Write leftover rows to file
        if leftover_rows:
            leftovers_path = os.path.join(os.path.dirname(file_path), 'import_analiz_takip_leftovers.tsv')
            with open(leftovers_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=reader.fieldnames, delimiter='\t')
                writer.writeheader()
                writer.writerows(leftover_rows)
            self.stdout.write(self.style.SUCCESS(f'Saved {len(leftover_rows)} rows to {leftovers_path}'))

        self.stdout.write(self.style.SUCCESS('Successfully imported analysis tracking data'))
