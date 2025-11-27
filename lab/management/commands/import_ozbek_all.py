import openpyxl
import json
import os
import csv
from datetime import datetime
from typing import Dict, List, Optional

import reversion
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone
from reversion.models import Version
from lab.importers.notes import ensure_note
from lab.importers.tracking import (
    evaluate_field_import,
    record_field_import,
    normalize_import_value,
)
from lab.models import (
    Analysis,
    AnalysisType,
    CrossIdentifier,
    Family,
    IdentifierType,
    Individual,
    Institution,
    Note,
    Project,
    Sample,
    SampleType,
    Status,
    Task,
    Test,
    TestType,
)
from ontologies.models import Term, Ontology
import re
from django.contrib.auth import get_user_model
from django.utils.text import slugify

User = get_user_model()


class ModelFieldUpdater:
    """Accumulate per-field update decisions before saving an object once."""

    def __init__(self, obj, admin_user: Optional[User], import_started_at: datetime):
        self.obj = obj
        self.admin_user = admin_user
        self.import_started_at = import_started_at
        self._pending_fields: List[str] = []
        self._tracker_updates: Dict[str, str] = {}

    def queue(self, field_name: str, new_value, current_value=None):
        decision = evaluate_field_import(
            self.obj, field_name, new_value, current_value=current_value
        )

        if decision.should_update_db:
            setattr(self.obj, field_name, new_value)
            if field_name not in self._pending_fields:
                self._pending_fields.append(field_name)

        if decision.should_update_tracker:
            self._tracker_updates[field_name] = decision.normalized_value

        return decision.should_update_db

    def commit(self):
        version: Optional[Version] = None
        if self._pending_fields:
            with reversion.create_revision():
                self.obj.save(update_fields=self._pending_fields)
                reversion.set_comment("import_ozbek_all")
                if self.admin_user:
                    reversion.set_user(self.admin_user)
                version = Version.objects.get_for_object(self.obj).first()

        for field_name, normalized_value in self._tracker_updates.items():
            record_field_import(
                self.obj,
                field_name,
                normalized_value,
                import_time=self.import_started_at,
                version=version,
            )

        self._pending_fields = []
        self._tracker_updates = {}


def sync_m2m_field(obj, field_name: str, manager, new_ids, import_started_at):
    """Update a many-to-many field with import tracking awareness."""

    target_ids = list(new_ids or [])
    current_ids = list(manager.values_list("id", flat=True))
    decision = evaluate_field_import(
        obj, field_name, target_ids, current_value=current_ids
    )

    if decision.should_update_db:
        manager.set(target_ids)

    if decision.should_update_tracker:
        record_field_import(
            obj,
            field_name,
            decision.normalized_value,
            import_time=import_started_at,
            version=None,
        )

    return decision


class Command(BaseCommand):
    help = 'Import data from OZBEK lab google sheets file'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the TSV file')
        parser.add_argument('--admin-username', type=str, help='Admin username for created_by fields')

    def _parse_date(self, date_str):
        """Parse date string in various formats"""
        if not date_str:
            return None

        # Handle datetime objects from Excel
        if hasattr(date_str, 'date'):
            return date_str.date()

        # Handle string dates
        if isinstance(date_str, str):
            formats = ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d.%m.%Y']
            for fmt in formats:
                try:
                    return datetime.strptime(date_str.strip(), fmt).date()
                except ValueError:
                    continue
        return None

    def _parse_ddmmyyyy(self, date_str):
        """Parse strict DD.MM.YYYY strings."""
        if not date_str or not isinstance(date_str, str):
            return None
        cleaned = date_str.strip()
        if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", cleaned):
            return None
        try:
            return datetime.strptime(cleaned, "%d.%m.%Y").date()
        except ValueError:
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
            
        institution, created = Institution.objects.get_or_create(
            name=name,
            defaults={
                'contact': contact or '',
                'created_by': admin_user
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created institution: {name}'))
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
        """Get HPO terms from newline-separated descriptions and codes"""
        if not hpo_codes_str:
            return []
            
        # Get the HP ontology
        hp_ontology = Ontology.objects.filter(type=1).first()  # 1 is HP in ONTOLOGY_CHOICES
        if not hp_ontology:
            self.stdout.write(self.style.WARNING('HP ontology not found'))
            return []
            
        # Split into individual terms (each term is "Description HP:code")
        terms = []
        
        # Split by newlines and filter out empty lines and '+' lines
        term_strings = []
        for line in hpo_codes_str.split('\n'):
            line = line.strip()
            if line and line != '+':
                term_strings.append(line)
        
        for term_str in term_strings:
            # Find the HP: code in the term string
            hp_match = re.search(r'HP:(\d+)', term_str)
            if not hp_match:
                self.stdout.write(self.style.WARNING(f'No HP code found in term: {term_str}'))
                continue
                
            code = hp_match.group(1)
            # Get the description (everything before the HP: code)
            description = term_str[:hp_match.start()].strip()
            
            # Find the term by identifier
            term = Term.objects.filter(
                ontology=hp_ontology,
                identifier=code
            ).first()
            
            if term:
                # self.stdout.write(self.style.SUCCESS(f'Found HPO term: {term.label} (HP:{code})'))
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
        
        self.stdout.write(self.style.SUCCESS(f'Total HPO terms found: {len(terms)}'))
        return terms



    def _parse_and_add_notes(self, note_text, target_obj, admin_user):
        """Parse newline-separated notes and add as separate Note objects.

        - Each non-empty line becomes a separate Note with full line as content
        - If a line begins with a date in format DD.MM.YYYY, set the earliest
          history record's history_date for that note to this date (midnight)
        """
        if not note_text:
            return
        # Ensure we have a content type for the target object
        try:
            ct = ContentType.objects.get_for_model(target_obj)
        except Exception:
            return

        lines = str(note_text).splitlines()
        for raw_line in lines:
            line = (raw_line or '').strip()
            if not line:
                continue
            # Create the note with the full line content
            note = ensure_note(
                target_obj=target_obj,
                content=line,
                user=admin_user,
                log_warning=self._log_warning,
            )
            if not note:
                continue

            # If line starts with a date, set the note's earliest history_date
            m = re.match(r'^(\d{2}\.\d{2}\.\d{4})', line)
            if m:
                try:
                    dt = datetime.strptime(m.group(1), '%d.%m.%Y')
                    # Ensure timezone-aware datetime to avoid warnings with USE_TZ
                    if timezone.is_naive(dt):
                        dt = timezone.make_aware(dt, timezone.get_current_timezone())
                    first_hist = note.history.earliest()
                    if first_hist:
                        first_hist.history_date = dt
                        first_hist.save()
                except Exception:
                    # If anything goes wrong, skip adjusting history date
                    pass

    def _log_warning(self, message: str):
        self.stdout.write(self.style.WARNING(message))

    def analysis_add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the TSV file')
        parser.add_argument(
            '--admin-user',
            type=str,
            help='Username of the admin user to use for created_by fields',
            required=True
        )

    def __analysis_parse_date(self, date_str):
        if not date_str or date_str.lower() == 'na':
            return None
        try:
            return datetime.strptime(date_str, '%d.%m.%Y').date()
        except ValueError:
            return None

    def _get_or_create_status(self, name, description, color, admin_user, content_type=None, icon=None):
        if not name:
            return None
        status, created = Status.objects.get_or_create(
            name=name,
            content_type=content_type,
            defaults={
                'description': description or '',
                'color': color or '#000000',
                'created_by': admin_user,
                'icon': icon,
            }
        )
        # Backfill or update icon if needed
        if icon and (created or not status.icon or status.icon != icon):
            status.icon = icon
            status.save()
        return status

    def _get_or_create_test_type(self, name, admin_user):
        if not name:
            return None
        test_type, created = TestType.objects.get_or_create(
            name=name,
            defaults={'created_by': admin_user}
        )
        return test_type

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
            status=Status.objects.get(name='Not Available', content_type=ContentType.objects.get(app_label='lab', model='sample')),
            isolation_by=admin_user,
            created_by=admin_user
        )
        return sample

    def _get_initials(self, full_name: str) -> str:
        parts = [p for p in (full_name or '').split() if p]
        return ''.join(part[0].upper() for part in parts)

    def _record_field_values(self, obj, field_names, version=None):
        """Record normalized field values for tracking."""
        for field_name in field_names:
            record_field_import(
                obj,
                field_name,
                normalize_import_value(getattr(obj, field_name, None)),
                import_time=self.import_started_at,
                version=version,
            )

    def _append_institution_contact_notes(self, institutions, contact_info, admin_user):
        if not contact_info:
            return
        for institution in institutions:
            ensure_note(
                target_obj=institution,
                content=f"Klinisyen & İletişim: {contact_info}",
                user=admin_user,
                log_warning=self._log_warning,
            )

    def _find_header_column(self, worksheet, column_name, *, search_rows=5):
        """Return (header_row_index, column_index) for a column name."""

        for idx, row in enumerate(
            worksheet.iter_rows(min_row=1, max_row=search_rows, values_only=True),
            start=1,
        ):
            values = list(row)
            if not any(values):
                continue
            for col_idx, cell_value in enumerate(values):
                if isinstance(cell_value, str) and cell_value.strip() == column_name:
                    return idx, col_idx
        return None, None

    def _get_individual_by_lab_id(self, lab_id):
        if not lab_id:
            return None
        identifier = str(lab_id).strip()
        if not identifier:
            return None
        return Individual.objects.filter(cross_ids__id_value=identifier).first()

    def _ensure_project(self, name, admin_user):
        project, _ = Project.objects.get_or_create(
            name=name,
            defaults={
                'description': '',
                'created_by': admin_user,
                'status': getattr(self, 'imported_project_status', None) or Status.objects.first(),
                'priority': 'medium'
            }
        )
        return project

    def _add_individual_to_project(self, project_name, individual, admin_user):
        project = self._ensure_project(project_name, admin_user)
        if project.individuals.filter(pk=individual.pk).exists():
            self.stdout.write(f'{individual.lab_id} already in project {project_name}')
            return False
        project.individuals.add(individual)
        self.stdout.write(self.style.SUCCESS(f'Added {individual.lab_id} to project {project_name}'))
        return True

    def _process_project_sheet(self, wb, sheet_name, id_column, project_name, admin_user):
        if sheet_name not in wb.sheetnames:
            self.stdout.write(f'Sheet "{sheet_name}" not found; skipping project import.')
            return
        ws = wb[sheet_name]
        header_row_idx, id_col_idx = self._find_header_column(ws, id_column)
        if id_col_idx is None:
            self.stdout.write(f'Column "{id_column}" not found in sheet "{sheet_name}". Skipping.')
            return
        processed = missing = 0
        for row in ws.iter_rows(min_row=header_row_idx + 1, values_only=True):
            if all(cell is None for cell in row):
                continue
            identifier = row[id_col_idx] if len(row) > id_col_idx else None
            if not identifier:
                continue
            if isinstance(identifier, (int, float)):
                if float(identifier).is_integer():
                    identifier = str(int(identifier))
                else:
                    identifier = str(identifier)
            identifier = str(identifier).strip()
            if not identifier or not any(ch.isalpha() for ch in identifier):
                continue
            individual = self._get_individual_by_lab_id(identifier)
            if not individual:
                missing += 1
                self._log_warning(f'{sheet_name}: individual not found for ID {identifier}')
                continue
            self._add_individual_to_project(project_name, individual, admin_user)
            processed += 1
        self.stdout.write(self.style.SUCCESS(f'{sheet_name}: processed {processed} rows, missing {missing}'))

    def _process_wgs_tuseb_sheet(self, wb, admin_user):
        sheet_name = 'WGS_TÜSEB'
        if sheet_name not in wb.sheetnames:
            self.stdout.write(f'Sheet "{sheet_name}" not found; skipping WGS_TÜSEB import.')
            return

        ws = wb[sheet_name]
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        headers = [h for h in headers if h is not None]

        performer_user, _ = User.objects.get_or_create(
            username='tuseb',
            defaults={
                'first_name': 'TÜSEB',
                'email': 'tuseb@example.com',
            },
        )
        test_type = self._get_or_create_test_type('WGS_TÜSEB', admin_user)
        processed = missing = 0

        for row in ws.iter_rows(min_row=2, values_only=True):
            if all(cell is None for cell in row):
                continue
            row = row[:len(headers)]
            row_dict = dict(zip(headers, row))
            lab_id = row_dict.get('Özbek Lab. ID')
            if not lab_id:
                continue
            individual = self._get_individual_by_lab_id(lab_id)
            if not individual:
                missing += 1
                self._log_warning(f'WGS_TÜSEB: individual not found for {lab_id}')
                continue

            self._add_individual_to_project('WGS_TÜSEB', individual, admin_user)
            sample = self._ensure_available_placeholder_sample(individual, admin_user)
            test = (
                Test.objects.filter(sample__individual=individual, test_type=test_type)
                .order_by('id')
                .first()
            )
            created = False
            if not test:
                with reversion.create_revision():
                    test = Test.objects.create(
                        sample=sample,
                        test_type=test_type,
                        status=self.test_status_pending,
                        service_send_date=self._parse_date(row_dict.get('Dizilemeye Gönderilme Tarihi')),
                        data_receipt_date=self._parse_date(row_dict.get('Data Gelme Tarihi')),
                        performed_by=performer_user,
                        created_by=admin_user,
                    )
                    reversion.set_comment('import_ozbek_all:wgs_tuseb_test')
                    if admin_user:
                        reversion.set_user(admin_user)
                self._record_field_values(
                    test,
                    ['status', 'service_send_date', 'data_receipt_date', 'performed_by'],
                    version=Version.objects.get_for_object(test).first(),
                )
                created = True
            else:
                if not test.sample_id:
                    test.sample = sample
                    test.save(update_fields=['sample'])

            updater = ModelFieldUpdater(test, admin_user, self.import_started_at)
            send_date = self._parse_date(row_dict.get('Dizilemeye Gönderilme Tarihi'))
            if send_date:
                updater.queue('service_send_date', send_date)
            receipt_date = self._parse_date(row_dict.get('Data Gelme Tarihi'))
            if receipt_date:
                updater.queue('data_receipt_date', receipt_date)
            updater.queue('performed_by', performer_user)
            status_name = row_dict.get('Data Geliş Durumu')
            if status_name:
                status_obj = self._ensure_status_for_model(
                    status_name,
                    ContentType.objects.get_for_model(Test),
                    admin_user,
                )
                if status_obj:
                    updater.queue('status', status_obj)
            updater.commit()

            data_notes = row_dict.get('Data Notları')
            if data_notes:
                self._parse_and_add_notes(data_notes, test, admin_user)

            processed += 1

        self.stdout.write(self.style.SUCCESS(f'WGS_TÜSEB: processed {processed} rows, missing {missing}'))

    def _ensure_available_placeholder_sample(self, individual, admin_user):
        placeholder_type = self._get_or_create_sample_type('Placeholder', admin_user)
        sample = Sample.objects.filter(individual=individual, sample_type=placeholder_type).order_by('id').first()
        if not sample:
            with reversion.create_revision():
                sample = Sample.objects.create(
                    individual=individual,
                    sample_type=placeholder_type,
                    status=self.sample_status_available,
                    receipt_date=None,
                    isolation_by=admin_user,
                    created_by=admin_user,
                )
                reversion.set_comment('import_ozbek_all:create_placeholder_sample')
                if admin_user:
                    reversion.set_user(admin_user)
            self._record_field_values(
                sample,
                ['status'],
                version=Version.objects.get_for_object(sample).first(),
            )
            return sample
        updater = ModelFieldUpdater(sample, admin_user, self.import_started_at)
        updater.queue('status', self.sample_status_available)
        updater.commit()
        return sample

    def _get_or_create_institution_user(self, name, admin_user):
        if not name:
            return admin_user
        base_slug = slugify(name) or "institution"
        slug = base_slug
        counter = 1
        while User.objects.filter(username=slug).exists():
            slug = f"{base_slug}_{counter}"
            counter += 1
        user, created = User.objects.get_or_create(
            username=slug,
            defaults={
                "email": f"{slug}@institution.local",
                "first_name": name[:30],
                "last_name": "",
            },
        )
        return user

    def _process_rna_seq_sheet(self, wb, admin_user):
        sheet_name = 'RNA SEQ'
        if sheet_name not in wb.sheetnames:
            self.stdout.write(f'Sheet "{sheet_name}" not found; skipping RNA Seq import.')
            return
        ws = wb[sheet_name]
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        headers = [h for h in headers if h is not None]
        processed = missing = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            if all(cell is None for cell in row):
                continue
            row = row[:len(headers)]
            row_dict = dict(zip(headers, row))
            lab_id = row_dict.get('Özbek Lab. ID')
            if not lab_id:
                continue
            individual = self._get_individual_by_lab_id(lab_id)
            if not individual:
                missing += 1
                self._log_warning(f'RNA SEQ: individual not found for {lab_id}')
                continue
            self._add_individual_to_project('RNA Seq', individual, admin_user)
            sample = self._ensure_available_placeholder_sample(individual, admin_user)
            test, _ = self._ensure_test_for_analysis(individual, 'RNA Seq', admin_user)
            if not test:
                continue
            if not test.sample_id:
                test.sample = sample
                test.save(update_fields=['sample'])
            sequencing_date = row_dict.get('Dizilemeye Gönderim Tarihi')
            upload_status = row_dict.get('Data Yüklenme Tarihi (G&More)/Status')
            if sequencing_date:
                ensure_note(
                    target_obj=test,
                    content=f"Dizilemeye Gönderim Tarihi: {sequencing_date}",
                    user=admin_user,
                    log_warning=self._log_warning,
                )
            if upload_status:
                ensure_note(
                    target_obj=test,
                    content=f"Data Yüklenme Tarihi (G&More)/Status: {upload_status}",
                    user=admin_user,
                    log_warning=self._log_warning,
                )
            processed += 1
        self.stdout.write(self.style.SUCCESS(f'RNA SEQ: processed {processed} rows, missing {missing}'))

    def _process_sanger_sheet(self, wb, admin_user):
        sheet_name = 'Sanger Konfirmasyonları'
        if sheet_name not in wb.sheetnames:
            self.stdout.write(f'Sheet "{sheet_name}" not found; skipping Sanger confirmations.')
            return
        ws = wb[sheet_name]
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        headers = [h for h in headers if h is not None]
        test_type = self._get_or_create_test_type('Sanger Confirmation', admin_user)
        processed = missing = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            if all(cell is None for cell in row):
                continue
            row = row[:len(headers)]
            row_dict = dict(zip(headers, row))
            lab_id = row_dict.get('Özbek Lab. ID')
            if not lab_id:
                continue
            individual = self._get_individual_by_lab_id(lab_id)
            if not individual:
                missing += 1
                self._log_warning(f'Sanger: individual not found for {lab_id}')
                continue
            sample = self._ensure_available_placeholder_sample(individual, admin_user)
            with reversion.create_revision():
                test = Test.objects.create(
                    sample=sample,
                    test_type=test_type,
                    status=self.test_status_completed,
                    created_by=admin_user,
                )
                reversion.set_comment('import_ozbek_all:sanger_test')
                if admin_user:
                    reversion.set_user(admin_user)
            with reversion.create_revision():
                analysis = Analysis.objects.create(
                    type=self.analysis_type_sanger,
                    status=self.analysis_status_completed,
                    performed_date=timezone.now().date(),
                    performed_by=admin_user,
                    test=test,
                    created_by=admin_user,
                )
                reversion.set_comment('import_ozbek_all:sanger_analysis')
                if admin_user:
                    reversion.set_user(admin_user)
            chrom_pos = row_dict.get('Chromosomal Position')
            sanger_status = row_dict.get('Sanger Conf. Status')
            if chrom_pos:
                ensure_note(
                    target_obj=analysis,
                    content=f"Chromosomal Position: {chrom_pos}",
                    user=admin_user,
                    log_warning=self._log_warning,
                )
            if sanger_status:
                ensure_note(
                    target_obj=analysis,
                    content=f"Sanger Confirmation Status: {sanger_status}",
                    user=admin_user,
                    log_warning=self._log_warning,
                )
            processed += 1
        self.stdout.write(self.style.SUCCESS(f'Sanger confirmations: processed {processed} rows, missing {missing}'))

    def _process_gennext_sheet(self, wb, admin_user):
        sheet_name = 'Gennext Analiz Listesi'
        if sheet_name not in wb.sheetnames:
            self.stdout.write(f'Sheet "{sheet_name}" not found; skipping Gennext analyses.')
            return
        ws = wb[sheet_name]
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        headers = [h for h in headers if h is not None]
        processed = missing = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            if all(cell is None for cell in row):
                continue
            row = row[:len(headers)]
            row_dict = dict(zip(headers, row))
            rb_id = row_dict.get('Gennext RBID')
            if not rb_id:
                continue
            individual = self._get_individual_by_lab_id(rb_id)
            if not individual:
                missing += 1
                self._log_warning(f'Gennext: individual not found for {rb_id}')
                continue
            test = self._get_existing_test_for_analysis(individual)
            if not test:
                self._log_warning(f'Gennext: no existing test found for {rb_id}, skipping analysis creation.')
                continue
            performed_date = self._parse_date(row_dict.get('Gennext Date')) or timezone.now().date()
            existing_analysis = (
                Analysis.objects.filter(
                    test=test,
                    type=self.analysis_type_gennext,
                    performed_date=performed_date,
                )
                .order_by('id')
                .first()
            )
            if existing_analysis:
                analysis = existing_analysis
            else:
                with reversion.create_revision():
                    analysis = Analysis.objects.create(
                        type=self.analysis_type_gennext,
                        status=self.analysis_status_in_progress,
                        performed_date=performed_date,
                        performed_by=admin_user,
                        test=test,
                        created_by=admin_user,
                    )
                    reversion.set_comment('import_ozbek_all:gennext_analysis')
                    if admin_user:
                        reversion.set_user(admin_user)
            gennext_hash = row_dict.get('Gennext Hash')
            if gennext_hash:
                ensure_note(
                    target_obj=analysis,
                    content=f"Gennext Hash: {gennext_hash}",
                    user=admin_user,
                    log_warning=self._log_warning,
                )
            processed += 1
        self.stdout.write(self.style.SUCCESS(f'Gennext analyses: processed {processed} rows, missing {missing}'))

    def _process_rarepipe_sheet(self, wb, admin_user):
        sheet_name = 'RarePipe Analiz Listesi'
        if sheet_name not in wb.sheetnames:
            self.stdout.write(f'Sheet "{sheet_name}" not found; skipping RarePipe analyses.')
            return
        ws = wb[sheet_name]
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        headers = [h for h in headers if h is not None]
        processed = missing = mismatch = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            if all(cell is None for cell in row):
                continue
            row = row[:len(headers)]
            row_dict = dict(zip(headers, row))
            rb_id = row_dict.get('RarePipe RBID')
            if not rb_id:
                continue
            rarepipe_value = row_dict.get('RarePipe')
            individual = self._get_individual_by_lab_id(rb_id)
            if not individual:
                missing += 1
                self._log_warning(f'RarePipe: individual not found for {rb_id}')
                continue
            if individual.lab_id and str(individual.lab_id).strip() != str(rb_id).strip():
                mismatch += 1
                self._log_warning(f'RarePipe: RBID mismatch for {rb_id} vs {individual.lab_id}')
            test = self._get_existing_test_for_analysis(individual)
            if not test:
                self._log_warning(
                    f'RarePipe: no existing test found for {rb_id}, skipping analysis creation.'
                )
                continue
            existing_analysis = (
                Analysis.objects.filter(
                    test=test,
                    type=self.analysis_type_rarepipe,
                )
                .order_by('id')
                .first()
            )
            if existing_analysis:
                analysis = existing_analysis
            else:
                with reversion.create_revision():
                    analysis = Analysis.objects.create(
                        type=self.analysis_type_rarepipe,
                        status=self.analysis_status_in_progress,
                        performed_date=timezone.now().date(),
                        performed_by=admin_user,
                        test=test,
                        created_by=admin_user,
                    )
                    reversion.set_comment('import_ozbek_all:rarepipe_analysis')
                    if admin_user:
                        reversion.set_user(admin_user)
            if rarepipe_value:
                ensure_note(
                    target_obj=analysis,
                    content=f"RarePipe: {rarepipe_value}",
                    user=admin_user,
                    log_warning=self._log_warning,
                )
            processed += 1
        self.stdout.write(self.style.SUCCESS(f'RarePipe analyses: processed {processed} rows, missing {missing}, mismatches {mismatch}'))

    def _process_genomize_sheet(self, wb, admin_user):
        primary_sheet = 'WGS_RB-dragen'
        legacy_sheet = 'WGS_RB / dragen'
        target_sheet = None
        if primary_sheet in wb.sheetnames:
            target_sheet = primary_sheet
        elif legacy_sheet in wb.sheetnames:
            target_sheet = legacy_sheet
            self._log_warning('Using legacy sheet name "WGS_RB / dragen"; please rename to "WGS_RB-dragen".')
        else:
            self.stdout.write(f'Sheet "{primary_sheet}" not found; skipping Genomize analyses.')
            return
        ws = wb[target_sheet]
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        headers = [h for h in headers if h is not None]
        processed = missing = skipped = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            if all(cell is None for cell in row):
                continue
            row = row[:len(headers)]
            row_dict = dict(zip(headers, row))
            lab_id = row_dict.get('Özbek Lab. ID')
            genomize_status = row_dict.get('GENOMİZE')
            if not lab_id or genomize_status is None:
                continue
            status_str = str(genomize_status).strip().upper()
            if status_str != 'YÜKLÜ':
                skipped += 1
                continue
            individual = self._get_individual_by_lab_id(lab_id)
            if not individual:
                missing += 1
                self._log_warning(f'Genomize: individual not found for {lab_id}')
                continue
            test = self._get_existing_test_for_analysis(individual)
            if not test:
                self._log_warning(f'Genomize: no existing test found for {lab_id}, skipping analysis creation.')
                continue
            with reversion.create_revision():
                Analysis.objects.create(
                    type=self.analysis_type_genomize,
                    status=self.analysis_status_completed,
                    performed_date=timezone.now().date(),
                    performed_by=admin_user,
                    test=test,
                    created_by=admin_user,
                )
                reversion.set_comment('import_ozbek_all:genomize_analysis')
                if admin_user:
                    reversion.set_user(admin_user)
            processed += 1
        self.stdout.write(self.style.SUCCESS(f'Genomize analyses: processed {processed}, missing {missing}, skipped {skipped}'))

    def _split_comma_field(self, raw_value):
        if not raw_value:
            return []
        return [piece.strip() for piece in str(raw_value).split(',') if piece and str(piece).strip()]

    def _choose_sample_for_test(self, individual, samples_touched, admin_user):
        if samples_touched:
            return samples_touched[0]
        sample = individual.samples.order_by('id').first()
        if sample:
            return sample
        return self._get_or_create_placeholder_sample(individual, admin_user)

    def _ensure_samples_from_row(self, individual, row_dict, admin_user):
        sample_types_raw = row_dict.get('Örnek Tipi')
        sample_type_names = self._split_comma_field(sample_types_raw)
        touched = []
        receipt_date = self._parse_date(row_dict.get('Geliş Tarihi/ay/gün/yıl'))

        for sample_type_name in sample_type_names:
            sample_type = self._get_or_create_sample_type(sample_type_name, admin_user)
            if not sample_type:
                continue

            sample_qs = Sample.objects.filter(individual=individual, sample_type=sample_type).order_by('id')
            sample = sample_qs.first()
            if not sample:
                status = self.sample_status_available if receipt_date else self.sample_status_pending_blood
                with reversion.create_revision():
                    sample = Sample.objects.create(
                        individual=individual,
                        sample_type=sample_type,
                        status=status,
                        receipt_date=receipt_date,
                        isolation_by=admin_user,
                        created_by=admin_user,
                    )
                    reversion.set_comment('import_ozbek_all:create_sample')
                    if admin_user:
                        reversion.set_user(admin_user)
                self._record_field_values(
                    sample,
                    ['status', 'receipt_date'],
                    version=Version.objects.get_for_object(sample).first(),
                )
            updater = ModelFieldUpdater(sample, admin_user, self.import_started_at)
            updater.queue('receipt_date', receipt_date)
            new_status = self.sample_status_available if receipt_date else self.sample_status_pending_blood
            updater.queue('status', new_status)
            updater.commit()
            touched.append(sample)

            izolasyon = row_dict.get('İzolasyonu yapan')
            if izolasyon:
                ensure_note(
                    target_obj=sample,
                    content=f"İzolasyonu yapan: {izolasyon}",
                    user=admin_user,
                    log_warning=self._log_warning,
                )

        sample_notes = row_dict.get('Örnek Notları')
        if sample_notes:
            for sample in touched:
                self._parse_and_add_notes(sample_notes, sample, admin_user)

        return touched

    def _ensure_status_for_model(self, status_name, content_type, admin_user, default_color='gray'):
        if not status_name:
            return None
        return self._get_or_create_status(
            status_name,
            '',
            default_color,
            admin_user,
            content_type,
        )

    def _ensure_test_for_analysis(self, individual, test_type_name, admin_user):
        test_type = self._get_or_create_test_type(test_type_name, admin_user)
        if not test_type:
            return None, False
        sample = individual.samples.order_by('id').first()
        if not sample:
            sample = self._get_or_create_placeholder_sample(individual, admin_user)
        test = Test.objects.filter(test_type=test_type, sample__individual=individual).order_by('id').first()
        created = False
        if not test:
            with reversion.create_revision():
                test = Test.objects.create(
                    sample=sample,
                    test_type=test_type,
                    status=self.test_status_pending,
                    created_by=admin_user,
                )
                reversion.set_comment('import_ozbek_all:create_analysis_test')
                if admin_user:
                    reversion.set_user(admin_user)
            self._record_field_values(
                test,
                ['status'],
                version=Version.objects.get_for_object(test).first(),
            )
            created = True
        return test, created

    def _get_existing_test_for_analysis(self, individual):
        """Return the earliest available test for an individual, if any."""

        return (
            Test.objects.filter(sample__individual=individual)
            .order_by('id')
            .first()
        )

    def _ensure_tests_from_row(self, individual, row_dict, admin_user, samples_touched):
        test_names = self._split_comma_field(row_dict.get('Çalışılan Test Adı'))
        tests = []
        default_sample = None
        if test_names:
            default_sample = self._choose_sample_for_test(individual, samples_touched, admin_user)

        for test_name in test_names:
            test_type = self._get_or_create_test_type(test_name, admin_user)
            if not test_type:
                continue

            test_qs = Test.objects.filter(sample__individual=individual, test_type=test_type).order_by('id')
            test = test_qs.first()
            created = False
            if not test:
                with reversion.create_revision():
                    test = Test.objects.create(
                        sample=default_sample,
                        test_type=test_type,
                        status=self.test_status_in_progress,
                        created_by=admin_user,
                    )
                    reversion.set_comment('import_ozbek_all:create_test')
                    if admin_user:
                        reversion.set_user(admin_user)
                self._record_field_values(
                    test,
                    ['status', 'data_receipt_date'],
                    version=Version.objects.get_for_object(test).first(),
                )
                created = True

            updater = ModelFieldUpdater(test, admin_user, self.import_started_at)
            updater.queue('status', self.test_status_in_progress)
            updater.commit()

            tests.append(
                {
                    'name': test_name,
                    'test': test,
                    'created': created,
                }
            )

        return tests

    def handle(self, *args, **options):

        self.import_started_at = timezone.now()
        call_command('create_ozbek_users') # Create groups and Ozbek users

        file_path = options['file_path']
        ozbek_lab_sheet = 'OZBEK LAB'
        analiz_takip_sheet = 'Analiz Takip'
        admin_username = options.get('admin_username')
        if not admin_username:
            self.stdout.write(self.style.ERROR('Please provide admin username with --admin-username'))
            return
        try:
            admin_user = User.objects.get(username=admin_username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Admin user {admin_username} not found'))
            return

        # --- CREATE ALL STATUSES FIRST ---
        self.stdout.write('Creating all required statuses...')
        
        # Individual statuses
        individual_statuses = {
            'Registered': {'description': 'Initial status for new entries', 'color': 'gray', 'icon': 'fa-user-plus'},
            'Solved': {'description': 'Entry has been completed', 'color': 'green', 'icon': 'fa-circle-check'}
        }
        for status_name, status_data in individual_statuses.items():
            status, created = Status.objects.get_or_create(
                name=status_name,
                content_type=ContentType.objects.get(app_label='lab', model='individual'),
                defaults={
                    'description': status_data['description'],
                    'color': status_data['color'],
                    'created_by': admin_user,
                    'icon': status_data.get('icon'),
                }
            )
            # Backfill icon if missing or different
            desired_icon = status_data.get('icon')
            if desired_icon and (created or not status.icon or status.icon != desired_icon):
                status.icon = desired_icon
                status.save()
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created individual status: {status_name}'))
            else:
                self.stdout.write(f'Individual status ensured: {status_name}')

        individual_ct = ContentType.objects.get(app_label='lab', model='individual')
        self.registered_individual_status = Status.objects.get(
            name='Registered',
            content_type=individual_ct,
        )

        # Sample statuses
        sample_ct = ContentType.objects.get(app_label='lab', model='sample')
        sample_statuses = {
            'placeholder': self._get_or_create_status(
                'Not Available',
                'A placeholder sample for tests performed off-center',
                'gray',
                admin_user,
                sample_ct,
                icon='fa-ban'
            ),
            'pending_blood_recovery': self._get_or_create_status(
                'Pending Blood Recovery',
                'Awaiting blood draw',
                'red',
                admin_user,
                sample_ct,
                icon='fa-droplet'
            ),
            'pending_isolation': self._get_or_create_status(
                'Pending Isolation',
                'Awaiting isolation of sample',
                'yellow',
                admin_user,
                sample_ct,
                icon='fa-vials'
            ),
            'available': self._get_or_create_status(
                'Available',
                'Available for tests',
                'green',
                admin_user,
                sample_ct,
                icon='fa-circle-check'
            ),
        }
        self.sample_status_available = sample_statuses['available']
        self.sample_status_pending_blood = sample_statuses['pending_blood_recovery']
        self.sample_status_placeholder = sample_statuses['placeholder']

        # Project statuses
        imported_project_status = self._get_or_create_status(
            'In Progress',
            'Project is in progress',
            'green',
            admin_user,
            ContentType.objects.get_for_model(Project),
            icon='fa-diagram-project'
        )
        
        self._get_or_create_status(
            'Setting Up',
            'Project is being set up',
            'yellow',
            admin_user,
            ContentType.objects.get_for_model(Project),
            icon='fa-gears'
        )
        
        self._get_or_create_status(
            'Completed',
            'Project is completed',
            'gray',
            admin_user,
            ContentType.objects.get_for_model(Project),
            icon='fa-flag-checkered'
        )

        # Analysis statuses and types
        analysis_ct = ContentType.objects.get_for_model(Analysis)
        self.analysis_status_completed = self._get_or_create_status(
            'Completed',
            'Analysis completed',
            'green',
            admin_user,
            analysis_ct,
            icon='fa-circle-check'
        )

        self.analysis_status_in_progress = self._get_or_create_status(
            'In Progress',
            'Analysis is in progress',
            'yellow',
            admin_user,
            analysis_ct,
            icon='fa-spinner'
        )

        self.analysis_status_pending = self._get_or_create_status(
            'Pending Data',
            'Analysis is pending data',
            'red',
            admin_user,
            analysis_ct,
            icon='fa-hourglass-half'
        )

        # Analysis types used across sheets
        self.analysis_type_variant = self._get_or_create_analysis_type(
            'Variant Analysis',
            '',
            admin_user
        )
        self.analysis_type_gennext = self._get_or_create_analysis_type(
            'Gennext',
            '',
            admin_user
        )
        self.analysis_type_sanger = self._get_or_create_analysis_type(
            'Sanger Confirmation',
            '',
            admin_user
        )
        self.analysis_type_rarepipe = self._get_or_create_analysis_type(
            'RarePipe',
            '',
            admin_user
        )
        self.analysis_type_genomize = self._get_or_create_analysis_type(
            'Genomize',
            '',
            admin_user
        )

        # Test statuses
        test_ct = ContentType.objects.get_for_model(Test)
        self.test_status_completed = self._get_or_create_status(
            'Completed',
            'Test completed',
            'green',
            admin_user,
            test_ct,
            icon='fa-circle-check'
        )

        self.test_status_in_progress = self._get_or_create_status(
            'In Progress',
            'Test is in progress',
            'yellow',
            admin_user,
            test_ct,
            icon='fa-spinner'
        )

        self.test_status_pending = self._get_or_create_status(
            'Pending',
            'Test is pending',
            'red',
            admin_user,
            test_ct,
            icon='fa-clock'
        )

        # Task statuses
        self._get_or_create_status(
            'Active',
            'Task is ongoing',
            'yellow',
            admin_user,
            ContentType.objects.get_for_model(Task),
            icon='fa-list-check'
        )

        self._get_or_create_status(
            'Completed',
            'Task is completed',
            'green',
            admin_user,
            ContentType.objects.get_for_model(Task),
            icon='fa-circle-check'
        )

        self._get_or_create_status(
            'Overdue',
            'Task is overdue',
            'red',
            admin_user,
            ContentType.objects.get_for_model(Task),
            icon='fa-triangle-exclamation'
        )

        # --- CREATE IdentifierType objects for cross IDs ---
        id_types = {}
        for idtype_name in ["RareBoost", "Biobank", "ERDERA"]:
            id_type, _ = IdentifierType.objects.get_or_create(
                name=idtype_name,
                defaults={
                    "description": f"{idtype_name} identifier type",
                    "created_by": admin_user
                }
            )
            id_types[idtype_name] = id_type

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

        # Note: Projects will now be created per-individual based on the new
        # 'Projeler' column in the OZBEK LAB sheet.

        # --- XLSX Reading ---
        wb = openpyxl.load_workbook(file_path, data_only=True)
        # --- INSTITUTION MAP SHEET (Coordinates) ---
        coords_map = {}
        try:
            ws_map = wb['Gönderen Kurum Harita']
            headers_map = [cell.value for cell in next(ws_map.iter_rows(min_row=1, max_row=1))]
            headers_map = [h for h in headers_map if h is not None]
            name_key = 'Kurum'
            coord_key = 'Harita'
            city_key = 'Şehir'
            official_name_key = 'Resmi Ad'
            total_rows = 0
            empty_rows = 0
            parsed_rows = 0
            skipped_no_name_or_coord = 0
            parse_errors = 0
            for row in ws_map.iter_rows(min_row=2, values_only=True):
                total_rows += 1
                if all(cell is None for cell in row):
                    empty_rows += 1
                    continue
                row = row[:len(headers_map)]
                row_dict = dict(zip(headers_map, row))
                raw_name = row_dict.get(name_key)
                coord_val = row_dict.get(coord_key)
                city_val = row_dict.get(city_key)
                official_name_val = row_dict.get(official_name_key)
                if not raw_name or not coord_val:
                    skipped_no_name_or_coord += 1
                    continue
                # Normalize and support multiple comma-separated names similar to source sheet
                for name in [n.strip() for n in str(raw_name).split(',') if n and str(n).strip()]:
                    try:
                        lat_str, lon_str = [p.strip() for p in str(coord_val).split(',')[:2]]
                        lat_val = float(lat_str)
                        lon_val = float(lon_str)
                        if name not in coords_map:
                            coords_map[name] = {}
                        coords_map[name]['coords'] = (lat_val, lon_val)
                        parsed_rows += 1
                    except Exception:
                        parse_errors += 1
                        continue
                    if city_val:
                        coords_map[name]['city'] = city_val.strip()
                    if official_name_val:
                        coords_map[name]['official_name'] = official_name_val.strip()
            self._institution_info = coords_map
            self._institution_coords = {
                name: data.get('coords')
                for name, data in coords_map.items()
                if data.get('coords')
            }
        except KeyError:
            # Sheet not present; proceed without coordinates
            self._institution_info = {}
            self._institution_coords = {}
            print("[Map Import] ERROR: coordinates sheet 'Gönderen Kurum Harita' not found; proceeding without coordinates")
        # --- OZBEK LAB SHEET ---
        ws_lab = wb[ozbek_lab_sheet]
        headers_lab = [cell.value for cell in next(ws_lab.iter_rows(min_row=1, max_row=1))]
        # Filter out None column names (empty columns at the end)
        headers_lab = [h for h in headers_lab if h is not None]
        
        # First pass: Collect unique values
        unique_family_ids = set()
        institution_details = {}
        for row in ws_lab.iter_rows(min_row=2, values_only=True):
            # Skip rows where all values are None (empty rows at the end)
            if all(cell is None for cell in row):
                continue
            # Truncate row to match filtered headers (remove empty columns)
            row = row[:len(headers_lab)]
            row_dict = dict(zip(headers_lab, row))
            lab_id = row_dict.get('Özbek Lab. ID')
            if not lab_id:
                self.stdout.write(f'Skipping row - missing lab ID. Row data: {row_dict}')
                continue
            if lab_id:
                family_id = self._get_family_id(lab_id)
                if family_id:
                    unique_family_ids.add(family_id)
            institution_name_raw = row_dict.get('Gönderen Kurum/Birim')
            contact_info = row_dict.get('Klinisyen & İletişim Bilgileri')
            if institution_name_raw:
                institution_names = [n.strip() for n in str(institution_name_raw).split(',') if n and str(n).strip()]
                for institution_name in institution_names:
                    if institution_name not in institution_details:
                        institution_details[institution_name] = set()
                    if contact_info:
                        institution_details[institution_name].add(contact_info)
        # Create Families
        families = {}
        for family_id in unique_family_ids:
            family, _ = Family.objects.get_or_create(
                family_id=family_id,
                defaults={'created_by': admin_user}
            )
            families[family_id] = family
        # Create Institutions with contact information (and coordinates if available)
        institutions = {}
        for name, contacts in institution_details.items():
            institution, _ = Institution.objects.get_or_create(
                name=name,
                defaults={
                    'contact': '\n'.join(contacts) if contacts else '',
                    'created_by': admin_user,
                    'latitude': self._institution_info.get(name, {}).get('coords', (None, None))[0] if self._institution_info.get(name) else 0.0,
                    'longitude': self._institution_info.get(name, {}).get('coords', (None, None))[1] if self._institution_info.get(name) else 0.0,
                    'city': self._institution_info.get(name, {}).get('city', ''),
                    'official_name': self._institution_info.get(name, {}).get('official_name', ''),
                }
            )
            if not _ and contacts:
                existing_contacts = set(institution.contact.split('\n')) if institution.contact else set()
                all_contacts = existing_contacts.union(contacts)
                institution.contact = '\n'.join(all_contacts)
                # Backfill coordinates if available and not set (or set to defaults)
                if name in self._institution_coords:
                    lat_val, lon_val = self._institution_coords[name]
                    if (institution.latitude in (None, 0.0)) and lat_val is not None:
                        institution.latitude = lat_val
                    if (institution.longitude in (None, 0.0)) and lon_val is not None:
                        institution.longitude = lon_val
                institution.save()
            institutions[name] = institution
        # Second pass: Create Individuals and CrossIdentifiers
        for row in ws_lab.iter_rows(min_row=2, values_only=True):
            # Skip rows where all values are None (empty rows at the end)
            if all(cell is None for cell in row):
                continue
            # Truncate row to match filtered headers (remove empty columns)
            row = row[:len(headers_lab)]
            row_dict = dict(zip(headers_lab, row))
            try:
                lab_id = row_dict.get('Özbek Lab. ID')
                if not lab_id:
                    self.stdout.write(f'Skipping row - missing lab ID. Row data: {row_dict}')
                    continue
                family_id = self._get_family_id(lab_id)
                if not family_id or family_id not in families:
                    self.stdout.write(f'Skipping row - invalid family_id: {family_id} for lab_id: {lab_id}')
                    continue
                institution_name_raw = row_dict.get('Gönderen Kurum/Birim')
                institution_list = []
                if institution_name_raw:
                    for inst_name in [n.strip() for n in str(institution_name_raw).split(',') if n and str(n).strip()]:
                        institution_list.append(institutions.get(inst_name, unknown_institution))
                if not institution_list:
                    institution_list = [unknown_institution]
                is_index = False
                if re.search(r'\.1(\.|$)', lab_id):
                    is_index = True
                full_name = row_dict.get('Ad-Soyad')
                if not full_name:
                    self.stdout.write(f'Skipping row - missing full_name for lab_id: {lab_id}')
                    continue
                individual = Individual.objects.filter(full_name=full_name, family=families[family_id]).first()
                if not individual:
                    tc_identity_val = row_dict.get('TC Kimlik No')
                    if tc_identity_val is not None:
                        if isinstance(tc_identity_val, str) and tc_identity_val.strip() == '':
                            tc_identity_val = None
                        elif isinstance(tc_identity_val, (int, float)):
                            tc_identity_val = int(tc_identity_val)
                        else:
                            try:
                                tc_identity_val = int(tc_identity_val)
                            except (TypeError, ValueError):
                                tc_identity_val = None
                    version = None
                    with reversion.create_revision():
                        individual = Individual.objects.create(
                            full_name=full_name,
                            family=families[family_id],
                            birth_date=self._parse_date(row_dict.get('Doğum Tarihi')),
                            icd11_code=row_dict.get('ICD11') or '',
                            status=self.registered_individual_status,
                            created_by=admin_user,
                            diagnosis='',
                            diagnosis_date=None,
                            council_date=self._parse_ddmmyyyy(row_dict.get('Konsey Tarihi')),
                            is_index=is_index,
                            tc_identity=tc_identity_val
                        )
                        reversion.set_comment('import_ozbek_all:create_individual')
                        if admin_user:
                            reversion.set_user(admin_user)
                        version = Version.objects.get_for_object(individual).first()
                    self._record_field_values(
                        individual,
                        [
                            'full_name',
                            'family',
                            'birth_date',
                            'icd11_code',
                            'status',
                            'council_date',
                            'is_index',
                            'tc_identity',
                        ],
                        version=version,
                    )
                    if institution_list:
                        individual.institution.set(institution_list)
                        record_field_import(
                            individual,
                            'institution',
                            normalize_import_value([inst.id for inst in institution_list]),
                            import_time=self.import_started_at,
                            version=version,
                        )
                        self._append_institution_contact_notes(
                            institution_list,
                            row_dict.get('Klinisyen & İletişim Bilgileri'),
                            admin_user,
                        )
                    self.stdout.write(self.style.SUCCESS(f"Created individual: {self._get_initials(full_name)}"))
                    # Add individual to projects listed in 'Projeler'
                    projects_field = row_dict.get('Projeler')
                    if projects_field:
                        project_names = [p.strip() for p in str(projects_field).split(',') if p and str(p).strip()]
                        for pname in project_names:
                            project_obj, _ = Project.objects.get_or_create(
                                name=pname,
                                defaults={
                                    'description': '',
                                    'created_by': admin_user,
                                    'status': imported_project_status,
                                    'priority': 'medium'
                                }
                            )
                            project_obj.individuals.add(individual)
                else:
                    if individual.is_index != is_index:
                        individual.is_index = is_index
                        individual.save()
                    self.stdout.write(f'Individual already exists: {self._get_initials(full_name)}')
                # Add individual-level notes (Kurum Notları)
                kurum_notes = row_dict.get('Kurum Notları')
                if kurum_notes:
                    self._parse_and_add_notes(kurum_notes, individual, admin_user)
                # Add individual-level follow-up notes (Takip Notları)
                takip_notes = row_dict.get('Takip Notları')
                if takip_notes:
                    self._parse_and_add_notes(takip_notes, individual, admin_user)
                # CrossIdentifiers
                rareboost_id = row_dict.get('Özbek Lab. ID')
                if rareboost_id:
                    CrossIdentifier.objects.get_or_create(
                        individual=individual,
                        id_type=id_types["RareBoost"],
                        defaults={
                            'id_value': rareboost_id,
                            'created_by': admin_user
                        }
                    )
                biobank_id = row_dict.get('Biyobanka ID')
                if biobank_id:
                    CrossIdentifier.objects.get_or_create(
                        individual=individual,
                        id_type=id_types["Biobank"],
                        defaults={
                            'id_value': biobank_id,
                            'created_by': admin_user
                        }
                    )
                erdera_id = row_dict.get('ERDERA ID')
                if erdera_id:
                    CrossIdentifier.objects.get_or_create(
                        individual=individual,
                        id_type=id_types["ERDERA"],
                        defaults={
                            'id_value': erdera_id,
                            'created_by': admin_user
                        }
                    )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Error processing row for {row_dict.get('Özbek Lab. ID')}: {str(e)}")
                )
                continue
        # --- END: Individual and CrossIdentifier logic ---
        # Create leftovers file in the same directory as input file
        leftovers_path = os.path.join(os.path.dirname(file_path), 'import_ozbek_lab_leftovers.tsv')
        leftover_rows = []
        for row in ws_lab.iter_rows(min_row=2, values_only=True):
            # Skip rows where all values are None (empty rows at the end)
            if all(cell is None for cell in row):
                continue
            # Truncate row to match filtered headers (remove empty columns)
            row = row[:len(headers_lab)]
            row_dict = dict(zip(headers_lab, row))
            lab_id = row_dict.get('Özbek Lab. ID')
            if not lab_id:
                self.stdout.write(f'Skipping row - missing lab ID. Row data: {row_dict}')
                leftover_rows.append(row_dict)
                continue
            try:
                individual = Individual.objects.filter(cross_ids__id_value=lab_id).first()
                if not individual:
                    self.stdout.write(f'Individual not found with lab_id: {lab_id}. Available cross_ids: {list(Individual.objects.values_list("cross_ids__id_value", flat=True))[:10]}')
                    leftover_rows.append(row_dict)
                    continue
                self.stdout.write(f'Found existing individual: {lab_id}')
            except Exception as e:
                leftover_rows.append(row_dict)
                self.stdout.write(self.style.WARNING(f'Error finding individual for {lab_id}: {str(e)}'))
                continue
            institution_name_raw = row_dict.get('Gönderen Kurum/Birim')
            institution_objs = []
            if institution_name_raw:
                for name in [n.strip() for n in str(institution_name_raw).split(',') if n and str(n).strip()]:
                    inst_obj = self._get_or_create_institution(
                        name,
                        row_dict.get('Klinisyen & İletişim Bilgileri'),
                        admin_user
                    )
                    if inst_obj:
                        institution_objs.append(inst_obj)
            if not institution_objs:
                institution_objs = [unknown_institution]
            is_index = False
            if re.search(r'\.1(\.|$)', lab_id):
                is_index = True
            updater = ModelFieldUpdater(individual, admin_user, self.import_started_at)

            full_name_candidate = row_dict.get('Ad-Soyad') or individual.full_name
            if full_name_candidate:
                updater.queue('full_name', full_name_candidate)

            tc_identity_val = row_dict.get('TC Kimlik No', individual.tc_identity)
            if tc_identity_val is not None:
                if isinstance(tc_identity_val, str) and tc_identity_val.strip() == '':
                    tc_identity_val = None
                elif isinstance(tc_identity_val, (int, float)):
                    tc_identity_val = int(tc_identity_val)
                else:
                    try:
                        tc_identity_val = int(tc_identity_val)
                    except (TypeError, ValueError):
                        tc_identity_val = None
            updater.queue('tc_identity', tc_identity_val)

            updater.queue('birth_date', self._parse_date(row_dict.get('Doğum Tarihi')))
            updater.queue('icd11_code', row_dict.get('ICD11') or '')
            sync_m2m_field(
                individual,
                'institution',
                individual.institution,
                [inst.id for inst in institution_objs],
                self.import_started_at,
            )
            self._append_institution_contact_notes(
                institution_objs,
                row_dict.get('Klinisyen & İletişim Bilgileri'),
                admin_user,
            )
            updater.queue('status', self.registered_individual_status)
            updater.queue('is_index', is_index)

            council_candidate = self._parse_ddmmyyyy(row_dict.get('Konsey Tarihi'))
            if council_candidate:
                updater.queue('council_date', council_candidate)

            updater.commit()
            # Add/ensure individual-project associations from 'Projeler'
            projects_field = row_dict.get('Projeler')
            if projects_field:
                project_names = [p.strip() for p in str(projects_field).split(',') if p and str(p).strip()]
                for pname in project_names:
                    project_obj, _ = Project.objects.get_or_create(
                        name=pname,
                        defaults={
                            'description': '',
                            'created_by': admin_user,
                            'status': imported_project_status,
                            'priority': 'medium'
                        }
                    )
                    project_obj.individuals.add(individual)
            hpo_terms = self._get_hpo_terms(row_dict.get('HPO kodları'))
            term_ids = [term.id for term in hpo_terms]
            sync_m2m_field(
                individual,
                'hpo_terms',
                individual.hpo_terms,
                term_ids,
                self.import_started_at,
            )
            if term_ids:
                self.stdout.write(self.style.SUCCESS(f'Updated {len(term_ids)} HPO terms for {self._get_initials(individual.full_name)}'))
            self.stdout.write(self.style.SUCCESS(f"Updated individual: {self._get_initials(individual.full_name)}"))
            samples_touched = self._ensure_samples_from_row(individual, row_dict, admin_user)
            tests_info = self._ensure_tests_from_row(individual, row_dict, admin_user, samples_touched)

            data_receipt = self._parse_date(row_dict.get('Data Geliş tarihi'))
            if data_receipt and tests_info:
                target_test = next((info['test'] for info in tests_info if not info['created']), None)
                if not target_test:
                    target_test = tests_info[0]['test']
                updater = ModelFieldUpdater(target_test, admin_user, self.import_started_at)
                updater.queue('data_receipt_date', data_receipt)
                updater.commit()
            elif data_receipt:
                fallback_test = Test.objects.filter(sample__individual=individual).order_by('id').first()
                if fallback_test:
                    updater = ModelFieldUpdater(fallback_test, admin_user, self.import_started_at)
                    updater.queue('data_receipt_date', data_receipt)
                    updater.commit()

            test_notes = self._split_comma_field(row_dict.get('Test Notları'))
            if tests_info and test_notes:
                for idx, info in enumerate(tests_info):
                    if idx >= len(test_notes):
                        break
                    ensure_note(
                        target_obj=info['test'],
                        content=test_notes[idx],
                        user=admin_user,
                        log_warning=self._log_warning,
                    )
                extra_notes = test_notes[len(tests_info):]
                for extra in extra_notes:
                    ensure_note(
                        target_obj=individual,
                        content=f"Test notu (eşleşmedi): {extra}",
                        user=admin_user,
                        log_warning=self._log_warning,
                    )
            elif test_notes:
                for note in test_notes:
                    ensure_note(
                        target_obj=individual,
                        content=f"Test notu (test bulunamadı): {note}",
                        user=admin_user,
                        log_warning=self._log_warning,
                    )
        self.stdout.write(self.style.WARNING(f'Leftover Rows: {len(leftover_rows)}'))
        if leftover_rows:
            with open(leftovers_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=headers_lab, delimiter='\t')
                writer.writeheader()
                writer.writerows(leftover_rows)
            self.stdout.write(self.style.WARNING(f'Saved {len(leftover_rows)} rows with missing data to {leftovers_path}'))
        self.stdout.write(self.style.SUCCESS('Data import completed successfully'))
        # --- ANALIZ TAKIP SHEET ---
        ws_analiz = wb[analiz_takip_sheet]
        headers_analiz = [cell.value for cell in next(ws_analiz.iter_rows(min_row=1, max_row=1))]
        # Filter out None column names (empty columns at the end)
        headers_analiz = [h for h in headers_analiz if h is not None]
        self.stdout.write(f'Analiz Takip sheet headers: {headers_analiz}')
        
        leftover_rows = []
        missing_veri_kaynagi_rows = []
        leftovers_path = os.path.join(os.path.dirname(file_path), 'import_analiz_takip_leftovers.tsv')

        for row in ws_analiz.iter_rows(min_row=2, values_only=True):
            # Skip rows where all values are None (empty rows at the end)
            if all(cell is None for cell in row):
                continue
            # Truncate row to match filtered headers (remove empty columns)
            row = row[:len(headers_analiz)]
            row_dict = dict(zip(headers_analiz, row))
            lab_id = row_dict.get('Özbek Lab. ID')
            if not lab_id:
                self.stdout.write(f'Skipping row with missing lab ID. Row data: {row_dict}')
                leftover_rows.append(row_dict)
                continue
            try:
                individual = Individual.objects.filter(cross_ids__id_value=lab_id).first()
                if not individual:
                    self.stdout.write(f'Individual not found with lab_id: {lab_id}. Available cross_ids: {list(Individual.objects.values_list("cross_ids__id_value", flat=True))[:10]}')
                    leftover_rows.append(row_dict)
                    continue
                # No default project assignment; projects handled via 'Projeler' in OZBEK LAB sheet
            except Exception as e:
                leftover_rows.append(row_dict)
                self.stdout.write(self.style.WARNING(f'Error finding individual for {lab_id}: {str(e)}'))
                continue
            veri_kaynagi = row_dict.get('VERİ KAYNAĞI')
            if not veri_kaynagi:
                self.stdout.write(f'Skipping row with missing VERİ KAYNAĞI for lab_id: {lab_id}. Available fields: {list(row_dict.keys())}')
                leftover_rows.append(row_dict)
                missing_veri_kaynagi_rows.append(row_dict)
                continue
            # Support multiple comma-separated test types in VERİ KAYNAĞI
            test_type_names = [p.strip() for p in str(veri_kaynagi).split(',') if p and str(p).strip()]
            if not test_type_names:
                leftover_rows.append(row_dict)
                self.stdout.write(self.style.WARNING(f'Skipping row with invalid/empty test type(s) for lab_id: {lab_id}'))
                continue
            tests_for_row = []
            for tt_name in test_type_names:
                test, _ = self._ensure_test_for_analysis(individual, tt_name, admin_user)
                if not test:
                    continue
                tests_for_row.append(test)

            if not tests_for_row:
                leftover_rows.append(row_dict)
                continue

            test_institutions = self._split_comma_field(row_dict.get('Verinin Geldiği Merkez'))
            performer_user = None
            if test_institutions:
                performer_user = self._get_or_create_institution_user(test_institutions[0], admin_user)

            test_status_name = row_dict.get('Status')
            data_receipt = self._parse_date(row_dict.get('Data Geliş Tarihi'))
            plan_notes = row_dict.get('PLAN')
            data_notes = row_dict.get('Data Notları')
            veri_icerigi = row_dict.get('Veri İçeriği')
            veri_notlari = row_dict.get('Veri Notları')
            test_notes = row_dict.get('Test Notları')

            for test in tests_for_row:
                if test_institutions:
                    for inst_name in test_institutions:
                        ensure_note(
                            target_obj=test,
                            content=f"Verinin Geldiği Merkez: {inst_name}",
                            user=admin_user,
                            log_warning=self._log_warning,
                        )
                if data_receipt:
                    updater = ModelFieldUpdater(test, admin_user, self.import_started_at)
                    updater.queue('data_receipt_date', data_receipt)
                    updater.commit()
                if test_status_name:
                    status_obj = self._ensure_status_for_model(
                        test_status_name,
                        ContentType.objects.get_for_model(Test),
                        admin_user,
                    )
                    if status_obj:
                        updater = ModelFieldUpdater(test, admin_user, self.import_started_at)
                        updater.queue('status', status_obj)
                        updater.commit()
                if plan_notes:
                    self._parse_and_add_notes(plan_notes, test, admin_user)
                if data_notes:
                    self._parse_and_add_notes(data_notes, test, admin_user)
                if veri_icerigi:
                    self._parse_and_add_notes(veri_icerigi, test, admin_user)
                if veri_notlari:
                    self._parse_and_add_notes(veri_notlari, test, admin_user)
                if test_notes:
                    self._parse_and_add_notes(test_notes, test, admin_user)
                if performer_user:
                    updater = ModelFieldUpdater(test, admin_user, self.import_started_at)
                    updater.queue('performed_by', performer_user)
                    updater.commit()

            analyses_created = []
            performed_date = self._parse_date(row_dict.get('Data yüklenme tarihi/emre')) or timezone.now().date()
            for test in tests_for_row:
                with reversion.create_revision():
                    analysis = Analysis.objects.create(
                        type=self.analysis_type_variant,
                        status=self.analysis_status_in_progress,
                        performed_date=performed_date,
                        performed_by=admin_user,
                        test=test,
                        created_by=admin_user
                    )
                    reversion.set_comment('import_ozbek_all:analysis_variant')
                    if admin_user:
                        reversion.set_user(admin_user)
                analyses_created.append(analysis)

            analysis_status_note = row_dict.get('ANALİZ STATUS')
            analysts = row_dict.get('ANALİZİ KİMLER YAPTI?')
            if analysis_status_note:
                for analysis in analyses_created:
                    ensure_note(
                        target_obj=analysis,
                        content=f"ANALİZ STATUS: {analysis_status_note}",
                        user=admin_user,
                        log_warning=self._log_warning,
                    )
            if analysts:
                for analysis in analyses_created:
                    ensure_note(
                        target_obj=analysis,
                        content=f"ANALİZİ KİMLER YAPTI?: {analysts}",
                        user=admin_user,
                        log_warning=self._log_warning,
                    )
        if missing_veri_kaynagi_rows:
            self.stdout.write(self.style.WARNING(f'{len(missing_veri_kaynagi_rows)} Analiz Takip rows missing VERİ KAYNAĞI'))
        if leftover_rows:
            with open(leftovers_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers_analiz, delimiter='\t')
                writer.writeheader()
                writer.writerows(leftover_rows)
            self.stdout.write(self.style.SUCCESS(f'Saved {len(leftover_rows)} rows to {leftovers_path}'))
        self.stdout.write(self.style.SUCCESS('Successfully imported analysis tracking data'))

        # --- PROJECT ENROLLMENT SHEETS ---
        project_sheet_specs = [
            ('Uzun Okuma Hastaları', 'RareBoost ID', 'Long Read'),
            ('TE NDD', 'Viable RareBoost ID', 'TE NDD'),
        ]
        for sheet_name, column, project_name in project_sheet_specs:
            self._process_project_sheet(wb, sheet_name, column, project_name, admin_user)

        self._process_wgs_tuseb_sheet(wb, admin_user)

        # --- RNA SEQ SHEET ---
        self._process_rna_seq_sheet(wb, admin_user)

        # --- SANGER CONFIRMATIONS ---
        self._process_sanger_sheet(wb, admin_user)

        # --- GENNEXT / RAREPIPE / GENOMIZE SHEETS ---
        self._process_gennext_sheet(wb, admin_user)
        self._process_rarepipe_sheet(wb, admin_user)
        self._process_genomize_sheet(wb, admin_user)

        # --- SET PARENTS (mother/father) BASED ON RAREBOOST ID SUFFIXES ---
        # Convention: familyId.1 = proband, .2 = mother, .3 = father,
        #             .1.1, .1.2 = affected siblings. We set parents for 1 and 1.* members.
        try:
            updated_links = 0
            for fam_id, fam_obj in families.items():
                # Build code -> individual map using RareBoost ID
                code_to_individual = {}
                for ind in fam_obj.individuals.all():
                    lab_id_val = ind.lab_id
                    if not lab_id_val or lab_id_val == 'No Lab ID':
                        continue
                    parts = str(lab_id_val).split('.')
                    if len(parts) < 2:
                        continue
                    code_str = '.'.join(parts[1:])
                    # Prefer the first occurrence if duplicates exist
                    code_to_individual.setdefault(code_str, ind)

                mother_individual = code_to_individual.get('2')
                father_individual = code_to_individual.get('3')
                if not mother_individual and not father_individual:
                    continue

                # Assign parents for proband (1) and siblings (1.*)
                for code_str, child in code_to_individual.items():
                    if code_str == '1' or code_str.startswith('1.'):
                        changed = False
                        if mother_individual and child.mother_id != mother_individual.id and child.id != mother_individual.id:
                            child.mother = mother_individual
                            changed = True
                        if father_individual and child.father_id != father_individual.id and child.id != father_individual.id:
                            child.father = father_individual
                            changed = True
                        if changed:
                            child.save()
                            updated_links += 1
            if updated_links:
                self.stdout.write(self.style.SUCCESS(f"Parent links set/updated for {updated_links} individual(s) based on RareBoost IDs"))
            else:
                self.stdout.write("No parent links needed/updated based on RareBoost IDs")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Error while setting parent links: {str(e)}"))
