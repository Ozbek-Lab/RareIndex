import csv
import os
import re
from django.core.management.base import BaseCommand
from django.apps import apps
from django.contrib.auth.models import User
from django.db import transaction
from datetime import datetime
from django.db.models.fields.related import ForeignKey

class Command(BaseCommand):
    help = 'Import data from TSV files into the database'

    def add_arguments(self, parser):
        parser.add_argument('directory', type=str, help='Directory containing TSV files')
        parser.add_argument('--app', type=str, default='lab', help='App name (default: lab)')

    def get_model_dependencies(self, model):
        """Get all models that this model depends on through ForeignKey relationships"""
        dependencies = set()
        for field in model._meta.get_fields():
            if isinstance(field, ForeignKey) and field.related_model != model:
                # Exclude self-referential dependencies (like mother/father in Individual)
                dependencies.add(field.related_model)
        return dependencies

    def sort_models_by_dependency(self, models_dict):
        """Sort models based on their dependencies, ensuring Family is processed first"""
        sorted_models = []
        visited = set()
        visiting = set()

        def visit(model_name):
            if model_name in visited:
                return
            if model_name in visiting:
                raise ValueError(f"Circular dependency detected for {model_name}")

            visiting.add(model_name)
            model = models_dict[model_name]
            dependencies = self.get_model_dependencies(model)

            for dep in dependencies:
                dep_name = dep.__name__
                if dep_name in models_dict and dep_name not in visited:
                    visit(dep_name)

            visiting.remove(model_name)
            visited.add(model_name)
            sorted_models.append(model_name)

        # Process Family first if it exists
        if 'Family' in models_dict:
            visit('Family')

        # Process remaining models
        for model_name in models_dict:
            if model_name not in visited:
                visit(model_name)

        return sorted_models

    def parse_family_id(self, lab_id):
        """Parse family ID from lab_id"""
        match = re.match(r'(RB_\d+_\d+)(?:\.\d+(?:\.\d+)?)?$', lab_id)
        return match.group(1) if match else None

    def get_individual_role(self, lab_id):
        """Determine individual's role based on lab_id pattern"""
        match = re.match(r'RB_\d+_\d+\.(\d+(?:\.\d+)?)', lab_id)
        if not match:
            return None
        
        suffix = match.group(1)
        if suffix == '1' or suffix.startswith('1.'):
            return 'proband'
        elif suffix == '2':
            return 'mother'
        elif suffix == '3':
            return 'father'
        else:
            return 'relative'
        return None

    def import_model_data(self, model, file_path, default_user):
        """Import data for a single model from a TSV file"""
        self.stdout.write(f"Importing {model.__name__} from {file_path}")
        
        try:
            with open(file_path, 'r') as file:
                reader = csv.DictReader(file, delimiter='\t')
                
                field_names = reader.fieldnames
                if not field_names:
                    self.stdout.write(self.style.ERROR(f'No headers found in {file_path}'))
                    return False

                model_fields = [f.name for f in model._meta.get_fields()]
                invalid_fields = [f for f in field_names if f not in model_fields]
                if invalid_fields:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Following fields in {file_path} are not in model: {", ".join(invalid_fields)}'
                        )
                    )

                # Store family objects for linking individuals
                families = {}
                individuals = {}
                objects_to_create = []
                row_number = 1

                for row in reader:
                    row_number += 1
                    try:
                        cleaned_data = {}
                        for field, value in row.items():
                            if field not in model_fields or not value:
                                continue

                            field_instance = model._meta.get_field(field)

                            # Special handling for lab_id in Individual model
                            if model.__name__ == 'Individual' and field == 'lab_id':
                                family_id = self.parse_family_id(value)
                                if family_id:
                                    # Get or create family
                                    if family_id not in families:
                                        family_model = apps.get_model(options['app'], 'Family')
                                        family, _ = family_model.objects.get_or_create(
                                            name=family_id,
                                            defaults={'created_by': default_user}
                                        )
                                        families[family_id] = family
                                    cleaned_data['family'] = families[family_id]

                            if field_instance.is_relation:
                                related_model = field_instance.related_model
                                if value.isdigit():
                                    try:
                                        related_obj = related_model.objects.get(id=value)
                                        cleaned_data[field] = related_obj
                                    except related_model.DoesNotExist:
                                        self.stdout.write(
                                            self.style.WARNING(
                                                f'Related object with id {value} not found for field {field} in row {row_number}'
                                            )
                                        )
                                else:
                                    try:
                                        if field in ['mother', 'father']:
                                            # For parent fields, look up by lab_id
                                            related_obj = related_model.objects.get(lab_id=value)
                                        else:
                                            lookup_fields = ['name', 'lab_id', 'id']
                                            for lookup_field in lookup_fields:
                                                if hasattr(related_model, lookup_field):
                                                    try:
                                                        related_obj = related_model.objects.get(**{lookup_field: value})
                                                        break
                                                    except related_model.DoesNotExist:
                                                        continue
                                            else:
                                                raise related_model.DoesNotExist
                                        cleaned_data[field] = related_obj
                                    except related_model.DoesNotExist:
                                        if field in ['mother', 'father']:
                                            # Store for later processing
                                            cleaned_data[f'_{field}_id'] = value
                                        else:
                                            self.stdout.write(
                                                self.style.WARNING(
                                                    f'Related object "{value}" not found for field {field} in row {row_number}'
                                                )
                                            )
                            elif isinstance(field_instance, models.DateTimeField):
                                try:
                                    cleaned_data[field] = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                                except ValueError:
                                    try:
                                        cleaned_data[field] = datetime.strptime(value, '%Y-%m-%d')
                                    except ValueError:
                                        self.stdout.write(
                                            self.style.WARNING(
                                                f'Invalid datetime format for field {field} in row {row_number}'
                                            )
                                        )
                            elif isinstance(field_instance, models.DateField):
                                try:
                                    cleaned_data[field] = datetime.strptime(value, '%Y-%m-%d').date()
                                except ValueError:
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'Invalid date format for field {field} in row {row_number}'
                                        )
                                    )
                            else:
                                cleaned_data[field] = value

                        # Add required fields if missing
                        if hasattr(model, 'created_by') and 'created_by' not in cleaned_data:
                            cleaned_data['created_by'] = default_user
                        if hasattr(model, 'performed_by') and 'performed_by' not in cleaned_data:
                            cleaned_data['performed_by'] = default_user
                        if hasattr(model, 'isolation_by') and 'isolation_by' not in cleaned_data:
                            cleaned_data['isolation_by'] = default_user

                        # Create the object
                        obj = model(**cleaned_data)
                        objects_to_create.append(obj)

                        # Store Individual objects for later parent linking
                        if model.__name__ == 'Individual' and 'lab_id' in cleaned_data:
                            individuals[cleaned_data['lab_id']] = obj

                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f'Error processing row {row_number} in {file_path}: {str(e)}'
                            )
                        )
                        continue

                # Bulk create objects
                try:
                    with transaction.atomic():
                        created_objects = model.objects.bulk_create(objects_to_create)
                        
                        # Update parent relationships for Individual objects
                        if model.__name__ == 'Individual':
                            for obj in created_objects:
                                mother_id = getattr(obj, '_mother_id', None)
                                father_id = getattr(obj, '_father_id', None)
                                
                                if mother_id and mother_id in individuals:
                                    obj.mother = individuals[mother_id]
                                if father_id and father_id in individuals:
                                    obj.father = individuals[father_id]
                                
                                if mother_id or father_id:
                                    obj.save()

                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Successfully imported {len(created_objects)} {model.__name__} objects'
                            )
                        )
                        return True
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f'Error bulk creating {model.__name__} objects: {str(e)}'
                        )
                    )
                    return False

        except FileNotFoundError:
            self.stdout.write(self.style.WARNING(f'File not found: {file_path}'))
            return False
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error reading {file_path}: {str(e)}'))
            return False

    def handle(self, *args, **options):
        print("Handle")
        print(f"options: {options}")
        directory = options['directory']
        app_name = 'lab'
        header_mapper = {
            'Özbek Lab. ID': 'individual__lab_id',
            "Biyobanka ID": "individual__biobank_id",
            "Ad-Soyad": "individual__full_name",
            "TC Kimlik No": "individual__tc_identity",
            "Doğum Tarihi": "individual__birth_date",
            "ICD11": "individual__icd11_code",
            "HPO kodları": "individual__hpo_codes",
            "Geliş Tarihi/ay/gün/yıl": "individual__receipt_date",
            "Gönderen Kurum/Birim": "individual__sending_institution",
            "Klinisyen & İletişim Bilgileri": "clinician__contact_info",
            "Örnek Tipi": "sample__sample_type",
            "İzolasyonu yapan": "sample__isolated_by",
            "Örnek gön.& OD değ.": "sample__QC",
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

        # Get default user for foreign key relationships if needed
        default_user = User.objects.first()
        if not default_user:
            self.stdout.write(self.style.ERROR('No user found in the database'))
            return

        # Get all TSV files in the directory
        try:
            files = [f for f in os.listdir(directory) if f.endswith('.tsv')]
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'Directory not found: {directory}'))
            return

        # Map model names to their classes
        models_dict = {}
        for file_name in files:
            print(file_name)
            model_name = file_name[:-4]  # Remove .tsv extension
            try:
                model = apps.get_model(app_name, model_name)
                models_dict[model_name] = model
            except LookupError:
                self.stdout.write(
                    self.style.WARNING(f'Model {model_name} not found in app {app_name}, skipping {file_name}')
                )

        if not models_dict:
            self.stdout.write(self.style.ERROR('No valid models found to import'))
            return

        # Sort models by dependency
        try:
            sorted_models = self.sort_models_by_dependency(models_dict)
        except ValueError as e:
            self.stdout.write(self.style.ERROR(str(e)))
            return

        # Import data for each model in order
        for model_name in sorted_models:
            model = models_dict[model_name]
            file_path = os.path.join(directory, f"{model_name}.tsv")
            self.import_model_data(model, file_path, default_user) 