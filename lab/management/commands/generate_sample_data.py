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
    PipelineType,
    Pipeline,
    Project,
    Task,
    IdentifierType,
    CrossIdentifier,
    Note
)
from ontologies.models import Term

class Command(BaseCommand):
    help = 'Generate sample data for testing'

    def add_arguments(self, parser):
        parser.add_argument('--families', type=int, default=3, help='Number of families to create')
        parser.add_argument('--samples-per-individual', type=int, default=2, help='Number of samples per individual')
        parser.add_argument('--tests-per-sample', type=int, default=2, help='Number of tests per sample')
        parser.add_argument('--pipelines-per-test', type=int, default=2, help='Number of pipelines per test')
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

        # Create pipeline types if they don't exist
        pipeline_types = self._create_pipeline_types(user)

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
            # Continue anyway, hpo_terms will be empty

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
                    pipeline_types,
                    options['samples_per_individual'],
                    options['tests_per_sample'],
                    options['pipelines_per_test'],
                    options['tasks_per_object'],
                    user,
                    all_statuses,
                    project
                )

        self.stdout.write(self.style.SUCCESS('Successfully generated sample data'))

    def _create_statuses(self, user):
        """Create statuses for each model type separately"""
        all_statuses = {}
        
        for model_type in [Individual, Sample, Test, Pipeline, Task]:
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
        types = ['DNA', 'RNA', 'Plasma', 'Serum', 'Whole Blood']
        created = {}
        for t in types:
            st, _ = SampleType.objects.get_or_create(name=t, defaults={'created_by': user})
            created[t.lower().replace(' ', '_')] = st
        return created

    def _create_test_types(self, user):
        types = ['WGS', 'WES', 'Panel']
        created = {}
        for t in types:
            tt, _ = TestType.objects.get_or_create(name=t, defaults={'created_by': user})
            created[t.lower()] = tt
        return created

    def _create_pipeline_types(self, user):
        types = ['Bioinformatics', 'Interpretation', 'Validation']
        created = {}
        for t in types:
            pt, _ = PipelineType.objects.get_or_create(name=t, defaults={'created_by': user})
            created[t.lower()] = pt
        return created

    def _get_or_create_institution(self, user):
        inst, _ = Institution.objects.get_or_create(name="Rare Disease Lab", defaults={'created_by': user})
        return inst

    def _create_project(self, user, status):
        proj, _ = Project.objects.get_or_create(
            name="Rare Disease Pilot",
            defaults={
                'description': "Pilot project for rare disease analysis",
                'status': status,
                'created_by': user,
                'created_at': timezone.now()
            }
        )
        return proj

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
                return str(erdera_id)
        
        return str(random.randint(1000000000, 9999999999))

    def _create_note(self, obj, user, text=None, creation_date=None):
        """Create a note for a given object."""
        # Note model does not have created_at field, it uses simple_history
        Note.objects.create(
            content_object=obj,
            content=text or f"Auto-generated note for {obj}",
            user=user
        )

    def _create_family(self, family_id, user, creation_date):
        fam = Family.objects.create(
            family_id=family_id,
            created_by=user
        )
        return fam

    def _create_individual(self, first_name, family, user, institution, status, hpo_terms, mother=None, father=None, is_index=False, creation_date=None):
        ind = Individual.objects.create(
            full_name=f"{first_name} {family.family_id}",
            family=family,
            mother=mother,
            father=father,
            is_index=is_index,
            sex=random.choice(['male', 'female']),
            birth_date=creation_date.date() - timedelta(days=random.randint(365*5, 365*50)),
            status=status,
            created_by=user,
            created_at=creation_date
        )
        ind.institution.add(institution)
        if hpo_terms:
            ind.hpo_terms.add(*random.sample(hpo_terms, random.randint(1, 5)))
        return ind

    def _create_tasks(self, obj, user, all_statuses, project, num_tasks, base_date):
        # Convert base_date to datetime if it's date
        if hasattr(base_date, 'date'):
            pass # it's datetime
        else:
            # assume it's date, convert to datetime
            base_date = timezone.datetime.combine(base_date, timezone.datetime.min.time()).replace(tzinfo=timezone.get_current_timezone())

        for i in range(num_tasks):
            Task.objects.create(
                title=f"Task {i+1} for {obj}",
                description=f"Auto-generated task",
                content_object=obj,
                project=project,
                status=all_statuses['task']['pending'],
                priority=random.choice(['low', 'medium', 'high']),
                assigned_to=user,
                created_by=user,
                due_date=base_date + timedelta(days=random.randint(1, 30))
            )

    def _create_samples(self, individual, sample_types, test_types, pipeline_types, num_samples, tests_per_sample, pipelines_per_test, tasks_per_object, user, all_statuses, project):
        for _ in range(num_samples):
            sample_type = random.choice(list(sample_types.values()))
            sample = Sample.objects.create(
                individual=individual,
                sample_type=sample_type,
                status=all_statuses['sample']['active'],
                receipt_date=timezone.now().date() - timedelta(days=random.randint(10, 100)),
                created_by=user,
                isolation_by=user
            )
            self._create_tasks(sample, user, all_statuses, project, tasks_per_object, sample.receipt_date)
            
            for _ in range(tests_per_sample):
                test_type = random.choice(list(test_types.values()))
                test = Test.objects.create(
                    sample=sample,
                    test_type=test_type,
                    status=all_statuses['test']['active'],
                    created_by=user,
                    performed_date=sample.receipt_date + timedelta(days=random.randint(1, 10)),
                    performed_by=user
                )
                self._create_tasks(test, user, all_statuses, project, tasks_per_object, test.performed_date)
                
                for _ in range(pipelines_per_test):
                    pipeline_type = random.choice(list(pipeline_types.values()))
                    pipeline = Pipeline.objects.create(
                        test=test,
                        type=pipeline_type,
                        status=all_statuses['pipeline']['active'],
                        created_by=user,
                        performed_date=test.performed_date + timedelta(days=random.randint(1, 5)),
                        performed_by=user
                    )
                    self._create_tasks(pipeline, user, all_statuses, project, tasks_per_object, pipeline.performed_date)
                    
                    self._create_variants(individual, pipeline, user, all_statuses)

    def _create_variants(self, individual, pipeline, user, all_statuses):
        """Create variants for an individual's pipeline"""
        from variant.models import SNV, CNV, SV, Repeat, Classification
        
        # Only create variants for some pipelines
        if random.random() > 0.7:
            return

        # Specific variants list provided by user
        specific_variants = [
            "chr10-77984023 A>G",
            "chr10-77982811 C>T",
            "chr10-78009515 C>T",
            "chr7-94053779 C>T",
            "chr1-241959054 CAA>C",
            "chrX-41437781 C>CCTAG",
            "chr1-6825194 G>T",
            "chr7-73683072 C>A",
            "chr20-22584278 T>C",
            "chr13-35645867 A>T",
            "chr4-84794563 C>T",
            "chr15-45152472 T>A",
            "chrX-155898245 AG>C",
            "chr8-96785174 CAA>C",
            "chr9-841776 C>G",
            "chr1-36091267 A>C",
            "chr20-50892050 TTCA>T",
            "chrX-120560586 T>C"
        ]

        # Create 1-3 variants from the list
        num_variants = random.randint(1, 3)
        selected_variants = random.sample(specific_variants, num_variants)
        
        for variant_str in selected_variants:
            # Parse variant string: "chr10-77984023 A>G"
            loc_part, alleles_part = variant_str.split(' ')
            chrom_part, pos_part = loc_part.split('-')
            ref, alt = alleles_part.split('>')
            
            chrom = chrom_part.replace('chr', '')
            start = int(pos_part)
            end = start + len(ref)
            
            common_args = {
                'individual': individual,
                'pipeline': pipeline,
                'chromosome': chrom,
                'start': start,
                'end': end,
                'created_by': user,
                'zygosity': random.choice(['het', 'hom', 'het', 'het']),
                'status': all_statuses['sample']['active']
            }
            
            # Create SNV (treating all as SNV/Indel which fits SNV model)
            variant = SNV.objects.create(
                **common_args,
                reference=ref,
                alternate=alt
            )
            
            # Note: Genes are linked automatically via signals
            
            # Add classification
            Classification.objects.create(
                variant=variant,
                user=user,
                classification=random.choice(['pathogenic', 'likely_pathogenic', 'vus', 'likely_benign', 'benign']),
                inheritance=random.choice(['ad', 'ar', 'de_novo', 'unknown']),
                notes="Auto-generated classification"
            )