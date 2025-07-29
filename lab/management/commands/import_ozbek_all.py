import openpyxl
import json
import os
import csv
from datetime import datetime
from django.core.management.base import BaseCommand
from django.core.management import call_command
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
    Analysis,
    AnalysisType,
    Note,
    IdentifierType,
    CrossIdentifier,
    Project
)
from ontologies.models import Term, Ontology
import re
from django.contrib.auth import get_user_model

User = get_user_model()


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
        placeholder_sample = self._get_or_create_sample(individual, placeholder_type, admin_user)
        
        # Create a placeholder sample
        sample = Sample.objects.create(
            individual=individual,
            sample_type=placeholder_type,
            status=Status.objects.get(name='Not Available', content_type=ContentType.objects.get(app_label='lab', model='sample')),
            isolation_by=admin_user,
            created_by=admin_user
        )
        return sample

    def handle(self, *args, **options):

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
            'Registered': {'description': 'Initial status for new entries', 'color': 'gray'},
            'Family': {'description': 'Is family member', 'color': 'yellow'},
            'Solved Family': {'description': 'Family is solved', 'color': 'green'},
            'Solved': {'description': 'Entry has been completed', 'color': 'green'}
        }
        for status_name, status_data in individual_statuses.items():
            _ , created = Status.objects.get_or_create(
                name=status_name,
                content_type=ContentType.objects.get(app_label='lab', model='individual'),
                defaults={
                    'description': status_data['description'],
                    'color': status_data['color'],
                    'created_by': admin_user,
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created individual status: {status_name}'))
            else:
                self.stdout.write(f'Individual status already exists: {status_name}')

        # Sample statuses
        sample_statuses = {
            'placeholder': self._get_or_create_status(
                'Not Available', 
                'A placeholder sample for tests performed off-center', 
                'gray', 
                admin_user, 
                ContentType.objects.get(app_label='lab', model='sample')
            ),
            'pending_blood_recovery': self._get_or_create_status(
                'Pending Blood Recovery', 
                'Awaiting blood draw', 
                'red', 
                admin_user, 
                ContentType.objects.get(app_label='lab', model='sample')
            ),
            'pending_isolation': self._get_or_create_status(
                'Pending Isolation', 
                'Awaiting isolation of sample', 
                'yellow', 
                admin_user, 
                ContentType.objects.get(app_label='lab', model='sample')
            ),
            'available': self._get_or_create_status(
                'Available', 
                'Available for tests', 
                'green', 
                admin_user, 
                ContentType.objects.get(app_label='lab', model='sample')
            ),
        }

        # Project statuses
        imported_project_status = self._get_or_create_status(
            'In Progress',
            'Project is in progress',
            'green',
            admin_user,
            ContentType.objects.get_for_model(Project)
        )
        
        self._get_or_create_status(
            'Setting Up',
            'Project is being set up',
            'yellow',
            admin_user,
            ContentType.objects.get_for_model(Project)
        )
        
        self._get_or_create_status(
            'Completed',
            'Project is completed',
            'gray',
            admin_user,
            ContentType.objects.get_for_model(Project)
        )

        # Analysis statuses
        completed_status = self._get_or_create_status(
            'Completed',
            'Analysis completed',
            'green',
            admin_user,
            ContentType.objects.get_for_model(Analysis)
        )

        self._get_or_create_status(
            'In Progress',
            'Analysis is in progress',
            'yellow',
            admin_user,
            ContentType.objects.get_for_model(Analysis)
        )

        self._get_or_create_status(
            'Pending Data',
            'Analysis is pending data',
            'red',
            admin_user,
            ContentType.objects.get_for_model(Analysis)
        )

        # Test statuses
        self._get_or_create_status(
            'Completed',
            'Test completed',
            'green',
            admin_user,
            ContentType.objects.get_for_model(Test)
        )

        self._get_or_create_status(
            'In Progress',
            'Test is in progress',
            'yellow',
            admin_user,
            ContentType.objects.get_for_model(Test)
        )

        self._get_or_create_status(
            'Pending',
            'Test is pending',
            'red',
            admin_user,
            ContentType.objects.get_for_model(Test)
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

        # Create or get the project for imported individuals
        imported_project, _ = Project.objects.get_or_create(
            name='RareBoost',
            defaults={
                'description': 'Boosting Rare Disease Research Capacity and Diagnosing Rare and Undiagnosed Patients',
                'created_by': admin_user,
                'status': Status.objects.get(name='In Progress', content_type=ContentType.objects.get(app_label='lab', model='project')),
                'priority': 'medium'
            }
        )

        # --- XLSX Reading ---
        wb = openpyxl.load_workbook(file_path, data_only=True)
        # --- OZBEK LAB SHEET ---
        ws_lab = wb[ozbek_lab_sheet]
        headers_lab = [cell.value for cell in next(ws_lab.iter_rows(min_row=1, max_row=1))]
        # Filter out None column names (empty columns at the end)
        headers_lab = [h for h in headers_lab if h is not None]
        self.stdout.write(f'OZBEK LAB sheet headers: {headers_lab}')
        
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
            institution_name = row_dict.get('Gönderen Kurum/Birim')
            contact_info = row_dict.get('Klinisyen & İletişim Bilgileri')
            if institution_name:
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
        # Create Institutions with contact information
        institutions = {}
        for name, contacts in institution_details.items():
            institution, _ = Institution.objects.get_or_create(
                name=name,
                defaults={
                    'contact': '\n'.join(contacts) if contacts else '',
                    'created_by': admin_user
                }
            )
            if not _ and contacts:
                existing_contacts = set(institution.contact.split('\n')) if institution.contact else set()
                all_contacts = existing_contacts.union(contacts)
                institution.contact = '\n'.join(all_contacts)
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
                institution_name = row_dict.get('Gönderen Kurum/Birim')
                institution = institutions.get(institution_name, unknown_institution)
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
                    individual = Individual.objects.create(
                        full_name=full_name,
                        family=families[family_id],
                        birth_date=self._parse_date(row_dict.get('Doğum Tarihi')),
                        icd11_code='',
                        institution=institution,
                        status=Status.objects.get(name='Registered', content_type=ContentType.objects.get(app_label='lab', model='individual')),
                        created_by=admin_user,
                        diagnosis='',
                        diagnosis_date=None,
                        council_date=None,
                        is_index=is_index,
                        tc_identity=tc_identity_val
                    )
                    self.stdout.write(self.style.SUCCESS(f'Created individual: {full_name}'))
                    imported_project.individuals.add(individual)
                else:
                    if individual.is_index != is_index:
                        individual.is_index = is_index
                        individual.save()
                    self.stdout.write(f'Individual already exists: {full_name}')
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
            institution = self._get_or_create_institution(
                row_dict.get('Gönderen Kurum/Birim'),
                row_dict.get('Klinisyen & İletişim Bilgileri'),
                admin_user
            )
            is_index = False
            if re.search(r'\.1(\.|$)', lab_id):
                is_index = True
            individual.full_name = row_dict.get('Ad-Soyad', individual.full_name)
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
            individual.tc_identity = tc_identity_val
            individual.birth_date = self._parse_date(row_dict.get('Doğum Tarihi')) or individual.birth_date
            individual.icd11_code = row_dict.get('ICD11', individual.icd11_code)
            individual.institution = institution if institution else individual.institution
            individual.status = Status.objects.get(name='Registered', content_type=ContentType.objects.get(app_label='lab', model='individual'))
            individual.is_index = is_index
            individual.save()
            imported_project.individuals.add(individual)
            hpo_terms = self._get_hpo_terms(row_dict.get('HPO kodları'))
            if hpo_terms:
                individual.hpo_terms.add(*hpo_terms)
                self.stdout.write(self.style.SUCCESS(f'Added {len(hpo_terms)} HPO terms to {individual.full_name}'))
            self.stdout.write(self.style.SUCCESS(f'Updated individual: {individual.full_name}'))
            sample_types = [s.strip() for s in (row_dict.get('Örnek Tipi') or '').split(',')]
            for sample_type_name in sample_types:
                if not sample_type_name:
                    continue
                sample_type = self._get_or_create_sample_type(sample_type_name, admin_user)
                if not sample_type:
                    continue
                isolation_by = self._get_or_create_user(row_dict.get('İzolasyonu yapan'), admin_user)
                existing_sample = None
                if sample_type_name in ["Tam Kan", "Tam Kan/Serum"]:
                    existing_sample = Sample.objects.filter(
                        individual=individual,
                        sample_type__name__in=["Tam Kan", "Tam Kan/Serum"]
                    ).first()
                else:
                    existing_sample = Sample.objects.filter(
                        individual=individual,
                        sample_type=sample_type
                    ).first()
                if existing_sample:
                    if not existing_sample.receipt_date:
                        existing_sample.receipt_date = self._parse_date(row_dict.get('Geliş Tarihi/ay/gün/yıl'))
                        if existing_sample.receipt_date:
                            existing_sample.status = Status.objects.get(name='Available', content_type=ContentType.objects.get(app_label='lab', model='sample'))
                    if not existing_sample.isolation_by:
                        existing_sample.isolation_by = isolation_by
                    if not existing_sample.status:
                        existing_sample.status = Status.objects.get(name='Available', content_type=ContentType.objects.get(app_label='lab', model='sample'))
                    existing_sample.save()
                    self.stdout.write(self.style.SUCCESS(f'Updated existing sample: {existing_sample}'))
                else:
                    initial_status = Status.objects.get(name='Available', content_type=ContentType.objects.get(app_label='lab', model='sample')) if self._parse_date(row_dict.get('Geliş Tarihi/ay/gün/yıl')) else Status.objects.get(name='Pending Blood Recovery', content_type=ContentType.objects.get(app_label='lab', model='sample'))
                    sample = Sample.objects.create(
                        individual=individual,
                        sample_type=sample_type,
                        status=initial_status,
                        receipt_date=self._parse_date(row_dict.get('Geliş Tarihi/ay/gün/yıl')),
                        isolation_by=isolation_by,
                        created_by=admin_user,
                    )
                    self.stdout.write(self.style.SUCCESS(f'Created new sample: {sample}'))
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
        
        gennext_type = self._get_or_create_analysis_type(
            'Gennext',
            '',
            admin_user
        )

        test_types = {}
        leftover_rows = []
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
                imported_project.individuals.add(individual)
            except Exception as e:
                leftover_rows.append(row_dict)
                self.stdout.write(self.style.WARNING(f'Error finding individual for {lab_id}: {str(e)}'))
                continue
            veri_kaynagi = row_dict.get('VERİ KAYNAĞI')
            if not veri_kaynagi:
                self.stdout.write(f'Skipping row with missing VERİ KAYNAĞI for lab_id: {lab_id}. Available fields: {list(row_dict.keys())}')
                leftover_rows.append(row_dict)
                continue
            test_type = self._get_or_create_test_type(veri_kaynagi, admin_user)
            if not test_type:
                leftover_rows.append(row_dict)
                self.stdout.write(self.style.WARNING(f'Skipping row with invalid test type for lab_id: {lab_id}'))
                continue
            test_types[veri_kaynagi] = test_type
            sample = individual.samples.first()
            if not sample:
                self.stdout.write(self.style.WARNING(f'AAAAAANo sample found for individual: {individual.full_name}'))
                sample = self._get_or_create_placeholder_sample(individual, admin_user)
            test = Test.objects.create(
                test_type=test_type,
                status=Status.objects.get(name='Completed', content_type=ContentType.objects.get(app_label='lab', model='test')),
                data_receipt_date=self._parse_date(row_dict.get('Data Geliş Tarihi')),
                sample=sample,
                created_by=admin_user
            )
            data_upload_date = self._parse_date(row_dict.get('Data yüklenme tarihi/emre'))
            if data_upload_date:
                analysis = Analysis.objects.create(
                    type=gennext_type,
                    status=Status.objects.get(name='In Progress', content_type=ContentType.objects.get(app_label='lab', model='analysis')),
                    performed_date=data_upload_date,
                    performed_by=admin_user,
                    test=test,
                    created_by=admin_user
                )
        if leftover_rows:
            with open(leftovers_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers_analiz, delimiter='\t')
                writer.writeheader()
                writer.writerows(leftover_rows)
            self.stdout.write(self.style.SUCCESS(f'Saved {len(leftover_rows)} rows to {leftovers_path}'))
        self.stdout.write(self.style.SUCCESS('Successfully imported analysis tracking data'))
