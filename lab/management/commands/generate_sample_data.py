import random
import time
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from lab.models import (
    Family,
    Individual,
    Sample,
    Test,
    Status,
    SampleType,
    Institution,
    TestType,
    AnalysisType,
    Analysis,
    Project,
    Task,
    IdentifierType,
    CrossIdentifier,
    Note  # Added Note import
)
from ontologies.models import Term

class Command(BaseCommand):
    help = 'Generate sample data for testing'

    def add_arguments(self, parser):
        parser.add_argument('--families', type=int, default=3, help='Number of families to create')
        parser.add_argument('--samples-per-individual', type=int, default=2, help='Number of samples per individual')
        parser.add_argument('--tests-per-sample', type=int, default=2, help='Number of tests per sample')
        parser.add_argument('--analyses-per-test', type=int, default=2, help='Number of analyses per test')
        parser.add_argument('--tasks-per-object', type=int, default=2, help='Number of tasks per object')


    def handle(self, *args, **options):
        # Get or create default user
        user = User.objects.first()
        if not user:
            self.stdout.write('Creating default superuser...')
            user = User.objects.create_superuser('admin', 'admin@example.com', 'admin')
            self.stdout.write('Creating pleb user...')
            pleb = User.objects.create_user('pleb', 'pleb@example.com', 'pleb')
            self.stdout.write('Creating normal user...')
            normal = User.objects.create_user('normal', 'normal@example.com', 'normal')

        # Create statuses if they don't exist
        all_statuses = self._create_statuses(user)

        # Create sample types if they don't exist
        sample_types = self._create_sample_types(user)

        # Create test types if they don't exist
        test_types = self._create_test_types(user)

        # Create analysis types if they don't exist
        analysis_types = self._create_analysis_types(user)

        # Create institution if it doesn't exist
        institution = self._get_or_create_institution(user)

        # Create 'Ongoing' status for Project if it doesn't exist
        project_content_type = ContentType.objects.get_for_model(Project)
        project_status, _ = Status.objects.get_or_create(
            name='Ongoing',
            content_type=project_content_type,
            defaults={
                'color': 'purple',
                'created_by': user
            }
        )

        # Create a project with 'Ongoing' status
        project = self._create_project(user, project_status)

        # Create identifier types if they don't exist
        identifier_types = self._create_identifier_types(user)

        # Get a random selection of HPO terms to use
        hpo_terms = list(Term.objects.filter(ontology__type=1).order_by('?')[:50])  # Get 50 random HPO terms
        self.stdout.write(f"Found {len(hpo_terms)} HPO terms to use")
        if not hpo_terms:
            self.stdout.write(self.style.WARNING('No HPO terms found in database!'))
            return

        # Generate families and their members

        all_individuals = []
        for i in range(options['families']):
            # Generate unique family ID that doesn't conflict with existing ones
            family_id = self._generate_unique_family_id(i+1)
            
            # Family creation date - start of the process
            family_creation_date = timezone.now() - timedelta(days=100)
            family = self._create_family(family_id, user, family_creation_date)
            self._create_note(family, user, creation_date=family_creation_date)
            self._create_tasks(family, user, all_statuses, project, options['tasks_per_object'], family_creation_date)
            
            # Mother creation date - after family creation
            mother_creation_date = family_creation_date + timedelta(days=random.randint(1, 3))
            mother = self._create_individual("Mother", family, user, institution, all_statuses['individual']['registered'], hpo_terms, is_index=False, creation_date=mother_creation_date)
            self._create_note(mother, user, creation_date=mother_creation_date)
            self._create_identifiers(mother, identifier_types, f"{family_id}.2", f"RD3.F{i+1:02d}.2", user )
            
            # Father creation date - after family creation
            father_creation_date = family_creation_date + timedelta(days=random.randint(1, 3))
            father = self._create_individual("Father", family, user, institution, all_statuses['individual']['registered'], hpo_terms, is_index=False, creation_date=father_creation_date)
            self._create_note(father, user, creation_date=father_creation_date)
            self._create_identifiers(father, identifier_types, f"{family_id}.3", f"RD3.F{i+1:02d}.3", user)
            all_individuals.extend([mother, father])
            multi_child = (i % 2 == 0)
            children = []
            if multi_child:
                for child_num in range(1, 3):
                    child_creation_date = family_creation_date + timedelta(days=random.randint(2, 5))
                    proband = self._create_individual(
                        f"Proband{child_num}", family, user, institution, all_statuses['individual']['active'], hpo_terms, mother=mother, father=father, is_index=True, creation_date=child_creation_date
                    )
                    self._create_note(proband, user, creation_date=child_creation_date)
                    rb_code = f"{family_id}.1.{child_num}"
                    biobank_code = f"RD3.F{i+1:02d}.1.{child_num}"
                    self._create_identifiers(proband, identifier_types, rb_code, biobank_code, user)
                    children.append(proband)
            else:
                child_creation_date = family_creation_date + timedelta(days=random.randint(2, 5))
                proband = self._create_individual(
                    "Proband", family, user, institution, all_statuses['individual']['active'], hpo_terms, mother=mother, father=father, is_index=True, creation_date=child_creation_date
                )
                self._create_note(proband, user, creation_date=child_creation_date)
                rb_code = f"{family_id}.1"
                biobank_code = f"RD3.F{i+1:02d}.1"
                self._create_identifiers(proband, identifier_types, rb_code, biobank_code, user)
                children.append(proband)
            all_individuals.extend(children)
            for individual in [mother, father] + children:
                # Create tasks for individual with future dates based on individual creation
                individual_created_at = individual.get_created_at()
                if individual_created_at:
                    individual_base_date = individual_created_at + timedelta(days=random.randint(1, 21))
                else:
                    individual_base_date = timezone.now() - timedelta(days=random.randint(1, 21))
                self._create_tasks(individual, user, all_statuses, project, options['tasks_per_object'], individual_base_date)
            for individual in [mother, father] + children:
                self._create_samples(
                    individual,
                    sample_types,
                    test_types,
                    analysis_types,
                    options['samples_per_individual'],
                    options['tests_per_sample'],
                    options['analyses_per_test'],
                    options['tasks_per_object'],
                    user,
                    all_statuses,
                    project
                )

        # Create additional projects and assign random individuals to them
        project_names = ["Cancer Study", "Rare Disease Cohort", "Control Group"]
        for pname in project_names:
            project_creation_date = timezone.now() - timedelta(days=100) - timedelta(days=random.randint(30, 365))
            proj = Project.objects.create(
                name=pname,
                description=f"Auto-generated project: {pname}",
                created_by=user,
                due_date=project_creation_date + timedelta(days=random.randint(60, 365)),
                status=project_status,
                priority=random.choice(["low", "medium", "high"])
            )
            # Assign a random subset of individuals to this project
            num_to_add = random.randint(2, min(8, len(all_individuals)))
            selected_inds = random.sample(all_individuals, num_to_add)
            proj.individuals.add(*selected_inds)
            self.stdout.write(f"Added {num_to_add} individuals to project '{pname}'")

        self.stdout.write(self.style.SUCCESS('Successfully generated sample data'))

    def _create_statuses(self, user):
        """Create statuses for each model type separately"""
        all_statuses = {}
        
        for model_type in [Individual, Sample, Test, Analysis, Task]:
            model_name = model_type.__name__
            status_data = {
                'registered': ('Registered', 'gray', 'fa-user-plus'),
                'active': ('Active', 'green', 'fa-play'),
                'completed': ('Completed', 'blue', 'fa-check-circle'),
                'cancelled': ('Cancelled', 'red', 'fa-times-circle'),
                'pending': ('Pending', 'yellow', 'fa-clock'),
            }
            
            model_statuses = {}
            for key, (name, color, icon) in status_data.items():
                status, _ = Status.objects.get_or_create(
                    name=name,
                    content_type=ContentType.objects.get_for_model(model_type),
                    defaults={
                        'color': color,
                        'icon': icon,
                        'created_by': user
                    }
                )
                # Update icon if it doesn't exist
                if not status.icon:
                    status.icon = icon
                    status.save()
                model_statuses[key] = status
            
            all_statuses[model_name.lower()] = model_statuses
        
        return all_statuses

    def _create_sample_types(self, user):
        sample_type_names = ['Blood', 'Tissue', 'Saliva', 'Urine']
        sample_types = []
        
        for name in sample_type_names:
            sample_type, _ = SampleType.objects.get_or_create(
                name=name,
                defaults={
                    'created_by': user
                }
            )
            sample_types.append(sample_type)
        
        return sample_types

    def _create_test_types(self, user):
        test_type_data = {
            'WGS': 'Whole Genome Sequencing',
            'WES': 'Whole Exome Sequencing',
            'RNA-Seq': 'RNA Sequencing',
            'Panel': 'Gene Panel Sequencing'
        }
        
        test_types = []
        for name, description in test_type_data.items():
            test_type, _ = TestType.objects.get_or_create(
                name=name,
                defaults={
                    'description': description,
                    'created_by': user
                }
            )
            test_types.append(test_type)
        
        return test_types

    def _create_analysis_types(self, user):
        analysis_type_data = {
            'QC': ('Quality Control', '1.0'),
            'Variant Calling': ('Variant Detection and Analysis', '2.1'),
            'CNV Analysis': ('Copy Number Variation Analysis', '1.5'),
            'RNA Expression': ('RNA Expression Analysis', '3.0')
        }
        
        analysis_types = []
        for name, (description, version) in analysis_type_data.items():
            analysis_type, _ = AnalysisType.objects.get_or_create(
                name=name,
                defaults={
                    'description': description,
                    'version': version,
                    'created_by': user
                }
            )
            analysis_types.append(analysis_type)
        
        return analysis_types

    def _get_or_create_institution(self, user):
        institution, _ = Institution.objects.get_or_create(
            name='Test Hospital',
            defaults={
                'created_by': user
            }
        )
        return institution

    def _create_project(self, user, status):
        project_creation_date = timezone.now() - timedelta(days=100) - timedelta(days=random.randint(30, 365))
        project, _ = Project.objects.get_or_create(
            name='Sample Data Project',
            defaults={
                'description': 'Project created by sample data generator',
                'created_by': user,
                'due_date': project_creation_date + timedelta(days=random.randint(60, 180)),
                'status': status
            }
        )
        return project

    def _create_family(self, family_id, user, creation_date=None):
        if creation_date is None:
            creation_date = timezone.now() - timedelta(days=100)
        family, _ = Family.objects.get_or_create(
            family_id=family_id,
            defaults={
                'description': f'Test family {family_id}',
                'created_by': user
            }
        )
        return family

    def _create_individual(self, role, family, user, institution, status, hpo_terms, mother=None, father=None, is_index=False, creation_date=None):
        if creation_date is None:
            creation_date = timezone.now() - timedelta(days=100)
        birth_date = timezone.now() - timedelta(days=100) - timedelta(days=random.randint(365*20, 365*50))
        individual = Individual.objects.create(
            full_name=f"{role} {family.family_id}",
            tc_identity=random.randint(1000000000, 9999999999),
            birth_date=birth_date,
            family=family,
            mother=mother,
            father=father,
            created_by=user,
            status=status,
            institution=institution,
            is_index=is_index
        )
        # Add random HPO terms (5-20 terms per individual)
        num_terms = random.randint(5, 20)
        selected_terms = random.sample(hpo_terms, min(num_terms, len(hpo_terms)))
        individual.hpo_terms.add(*selected_terms)
        # Set is_affected based on HPO terms
        individual.is_affected = len(selected_terms) > 0
        individual.save()
        self.stdout.write(f"Added {len(selected_terms)} HPO terms to {individual.full_name} (is_index={is_index})")
        return individual

    def _create_tasks(self, obj, user, all_statuses, project, num_tasks, base_date=None):
        priorities = ['low', 'medium', 'high', 'urgent']
        if base_date is None:
            base_date = timezone.now() - timedelta(days=100)
        
        for i in range(num_tasks):
            # Tasks should be due in the future relative to the base date
            task_due_date = base_date + timedelta(days=random.randint(7, 60))
            task_creation_date = base_date + timedelta(days=random.randint(0, 2))
            
            # Randomly assign a task status (mostly pending/active, some completed)
            status_weights = {
                'pending': 0.4,
                'active': 0.4,
                'completed': 0.15,
                'cancelled': 0.05
            }
            task_status = random.choices(
                list(status_weights.keys()),
                weights=list(status_weights.values())
            )[0]
            
            task = Task.objects.create(
                title=f'Task {i+1}',
                description=f'Auto task {i+1}',
                content_object=obj,
                assigned_to=user,
                created_by=user,
                due_date=task_due_date,
                priority=random.choice(priorities),
                status=all_statuses['task'][task_status],
                project=project
            )
            self._create_note(task, user, text=f"Auto note for Task {i+1}", creation_date=task_creation_date)

    def _create_samples(self, individual, sample_types, test_types, analysis_types, num_samples, tests_per_sample, analyses_per_test, tasks_per_object, user, all_statuses, project):
        for i in range(num_samples):
            # Start with a realistic base date for this sample (after individual creation)
            individual_created_at = individual.get_created_at()
            if individual_created_at:
                base_date = individual_created_at + timedelta(days=random.randint(7, 30))
            else:
                base_date = timezone.now() - timedelta(days=random.randint(7, 30))
            
            # Sample receipt date (when sample arrives at lab)
            sample_receipt_date = base_date
            
            # Sample creation date (when sample is processed/isolated) - 1-3 days after receipt
            sample_creation_date = sample_receipt_date + timedelta(days=random.randint(1, 3))
            
            # Create sample with realistic creation/update dates
            sample = Sample.objects.create(
                individual=individual,
                sample_type=random.choice(sample_types),
                status=all_statuses['sample']['registered'],
                receipt_date=sample_receipt_date,
                isolation_by=user,
                created_by=user
            )
            self._create_note(sample, user, creation_date=sample_creation_date)

            # Create tasks for sample (due 1-2 weeks after sample creation)
            self._create_tasks(sample, user, all_statuses, project, tasks_per_object, sample_creation_date)

            # Create tests for sample
            for j in range(tests_per_sample):
                # Test performed date - 3-7 days after sample creation
                test_performed_date = sample_creation_date + timedelta(days=random.randint(3, 7))
                
                test = Test.objects.create(
                    test_type=random.choice(test_types),
                    performed_date=test_performed_date,
                    performed_by=user,
                    sample=sample,
                    created_by=user,
                    status=all_statuses['test']['active']
                )
                self._create_note(test, user, creation_date=test_performed_date)

                # Create tasks for test (due 1-2 weeks after test performance)
                self._create_tasks(test, user, all_statuses, project, tasks_per_object, test_performed_date)

                # Create analyses for test
                for k in range(analyses_per_test):
                    # Analysis performed date - 1-5 days after test performance
                    analysis_performed_date = test_performed_date + timedelta(days=random.randint(1, 5))
                    
                    analysis = Analysis.objects.create(
                        test=test,
                        performed_date=analysis_performed_date,
                        performed_by=user,
                        type=random.choice(analysis_types),
                        status=all_statuses['analysis']['active'],
                        created_by=user
                    )
                    self._create_note(analysis, user, creation_date=analysis_performed_date)

                    # Create tasks for analysis (due 1-2 weeks after analysis performance)
                    self._create_tasks(analysis, user, all_statuses, project, tasks_per_object, analysis_performed_date)

    def _create_identifier_types(self, user):
        identifier_type_data = {
            'RareBoost': 'RareBoost',
            'Biobank': 'Biobank',
            'ERDERA': 'ERDERA'
        }
        for name, description in identifier_type_data.items():
            IdentifierType.objects.get_or_create(name=name, defaults={'description': description, 'created_by': user})
        return IdentifierType.objects.all()

    def _create_identifiers(self, individual, identifier_types, lab_id, biobank_id, user):
            # Create RareBoost identifier (check for uniqueness and avoid duplicates for same individual)
            if not CrossIdentifier.objects.filter(id_type=identifier_types[0], id_value=lab_id).exists():
                if not CrossIdentifier.objects.filter(individual=individual, id_type=identifier_types[0]).exists():
                    CrossIdentifier.objects.create(
                        individual=individual,
                        id_type=identifier_types[0],
                        id_value=lab_id,
                        link=f"https://www.rareboost.com/individual/{lab_id}",
                        created_by=user
                    )
            
            # Create Biobank identifier (check for uniqueness and avoid duplicates for same individual)
            if not CrossIdentifier.objects.filter(id_type=identifier_types[1], id_value=biobank_id).exists():
                if not CrossIdentifier.objects.filter(individual=individual, id_type=identifier_types[1]).exists():
                    CrossIdentifier.objects.create(
                        individual=individual,
                        id_type=identifier_types[1],
                        id_value=biobank_id,
                        link=f"https://www.biobank.com/individual/{biobank_id}",
                        created_by=user
                    )
            
            # Create ERDERA identifier (generate unique random ID and avoid duplicates for same individual)
            if not CrossIdentifier.objects.filter(individual=individual, id_type=identifier_types[2]).exists():
                erdera_id = self._generate_unique_erdera_id()
                CrossIdentifier.objects.create(
                    individual=individual,
                    id_type=identifier_types[2],
                    id_value=erdera_id,
                    link=f"https://www.erdera.com/individual/{erdera_id}",
                    created_by=user
                )

    def _generate_unique_family_id(self, family_number):
        """Generate a unique family ID that doesn't conflict with existing ones."""
        from lab.models import Family
        import time
        
        # Start with the base pattern
        base_id = f"RB_2025_{family_number:02d}"
        
        # Check if this ID already exists
        counter = 0
        family_id = base_id
        while Family.objects.filter(family_id=family_id).exists():
            counter += 1
            family_id = f"{base_id}_{counter}"
        
        return family_id

    def _generate_unique_erdera_id(self):
        """Generate a unique ERDERA ID that doesn't conflict with existing ones."""
        from lab.models import CrossIdentifier
        from lab.models import IdentifierType
        
        # Get the ERDERA identifier type
        erdera_type = IdentifierType.objects.filter(name='ERDERA').first()
        if not erdera_type:
            # If ERDERA type doesn't exist, just return a random number
            return random.randint(1000000000, 9999999999)
        
        # Generate a unique random ID
        max_attempts = 100
        for attempt in range(max_attempts):
            erdera_id = random.randint(1000000000, 9999999999)
            if not CrossIdentifier.objects.filter(id_type=erdera_type, id_value=str(erdera_id)).exists():
                return erdera_id
        
        # If we can't find a unique ID after max attempts, add a timestamp
        return int(f"{random.randint(100000000, 999999999)}{int(time.time()) % 10000}")

    def _create_note(self, obj, user, text=None, creation_date=None):
        """Create a note for the given object if it supports notes."""
        if hasattr(obj, 'notes'):
            if creation_date is None:
                creation_date = timezone.now() - timedelta(days=100) + timedelta(days=random.randint(3, 5))
            Note.objects.create(
                content_object=obj,
                content=text or f"Auto-generated note for {obj}",
                user=user
            )