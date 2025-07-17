import random
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
    CrossIdentifier
)
from ontologies.models import Term

class Command(BaseCommand):
    help = 'Generate sample data for testing'

    def add_arguments(self, parser):
        parser.add_argument('--families', type=int, default=5, help='Number of families to create')
        parser.add_argument('--samples-per-individual', type=int, default=3, help='Number of samples per individual')
        parser.add_argument('--tests-per-sample', type=int, default=2, help='Number of tests per sample')
        parser.add_argument('--analyses-per-test', type=int, default=2, help='Number of analyses per test')
        parser.add_argument('--tasks-per-object', type=int, default=2, help='Number of tasks per object')

    def handle(self, *args, **options):
        # Get or create default user
        user = User.objects.first()
        if not user:
            self.stdout.write('Creating default superuser...')
            user = User.objects.create_superuser('admin', 'admin@example.com', 'admin')
            self.stdout.write('Creating pleb and normal users...')
            User.objects.create_user('pleb', 'pleb@example.com', 'pleb')
            User.objects.create_user('normal', 'normal@example.com', 'normal')

        # Create statuses if they don't exist
        statuses = self._create_statuses(user)
        
        # Create sample types if they don't exist
        sample_types = self._create_sample_types(user)

        # Create test types if they don't exist
        test_types = self._create_test_types(user)

        # Create analysis types if they don't exist
        analysis_types = self._create_analysis_types(user)

        # Create institution if it doesn't exist
        institution = self._get_or_create_institution(user)

        # Create a project
        project = self._create_project(user)

        # Create identifier types if they don't exist
        identifier_types = self._create_identifier_types(user)

        # Get a random selection of HPO terms to use
        hpo_terms = list(Term.objects.filter(ontology__type=1).order_by('?')[:50])  # Get 50 random HPO terms
        self.stdout.write(f"Found {len(hpo_terms)} HPO terms to use")
        if not hpo_terms:
            self.stdout.write(self.style.WARNING('No HPO terms found in database!'))
            return

        # Generate families and their members
        for i in range(options['families']):
            family_id = f"RB_2025_{i+1:02d}"
            family = self._create_family(family_id, user)
            
            # Create tasks for family
            self._create_tasks(family, user, statuses['completed'], project, options['tasks_per_object'])
            
            # Create family members
            mother = self._create_individual("Mother", family, user, institution, statuses['registered'], hpo_terms)
            self._create_identifiers(mother, identifier_types, f"{family_id}.2", f"RD3.F{i+1:02d}.2", user )
            father = self._create_individual("Father", family, user, institution, statuses['registered'], hpo_terms)
            self._create_identifiers(father, identifier_types, f"{family_id}.3", f"RD3.F{i+1:02d}.3", user)

            # Create proband (sick child)
            proband = self._create_individual(
                "Proband",
                family,
                user,
                institution,
                statuses['active'],
                hpo_terms,
                mother=mother,
                father=father
            )
            self._create_identifiers(proband, identifier_types, f"{family_id}.1", f"RD3.F{i+1:02d}.1", user)

            # Create tasks for individuals
            for individual in [proband, mother, father]:
                self._create_tasks(individual, user, statuses['completed'], project, options['tasks_per_object'])

            # Create samples for each individual
            for individual in [proband, mother, father]:
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
                    statuses,
                    project
                )

        self.stdout.write(self.style.SUCCESS('Successfully generated sample data'))

    def _create_statuses(self, user):
        for type in [Individual, Sample, Test, Analysis]:
            status_data = {
                'registered': ('Registered', 'gray'),
                'active': ('Active', 'green'),
                'completed': ('Completed', 'blue'),
                'cancelled': ('Cancelled', 'red'),
                'pending': ('Pending', 'yellow'),
            }
            
            statuses = {}
            for key, (name, color) in status_data.items():
                status, _ = Status.objects.get_or_create(
                    name=name,
                    content_type=ContentType.objects.get_for_model(type),
                    defaults={
                        'color': color,
                        'created_by': user
                    }
                )
                statuses[key] = status
            
            return statuses

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

    def _create_project(self, user):
        project, _ = Project.objects.get_or_create(
            name='Sample Data Project',
            defaults={
                'description': 'Project created by sample data generator',
                'created_by': user,
                'due_date': timezone.now() + timedelta(days=90)
            }
        )
        return project

    def _create_family(self, family_id, user):
        family, _ = Family.objects.get_or_create(
            family_id=family_id,
            defaults={
                'description': f'Test family {family_id}',
                'created_by': user
            }
        )
        return family

    def _create_individual(self, role, family, user, institution, status, hpo_terms, mother=None, father=None):
        birth_date = timezone.now() - timedelta(days=random.randint(365*20, 365*50))
        
        individual = Individual.objects.create(
            full_name=f"{role} {family.family_id}",
            tc_identity=random.randint(1000000000, 9999999999),
            birth_date=birth_date,
            family=family,
            mother=mother,
            father=father,
            created_by=user,
            status=status,
            sending_institution=institution
        )
        
        # Add random HPO terms (5-20 terms per individual)
        num_terms = random.randint(5, 20)
        selected_terms = random.sample(hpo_terms, min(num_terms, len(hpo_terms)))
        individual.hpo_terms.add(*selected_terms)
        
        self.stdout.write(f"Added {len(selected_terms)} HPO terms to {individual.lab_id}")
        
        return individual

    def _create_tasks(self, obj, user, target_status, project, num_tasks):
        priorities = ['low', 'medium', 'high', 'urgent']
        for i in range(num_tasks):
            Task.objects.create(
                title=f'Task {i+1} for {obj}',
                description=f'Sample task {i+1} created for {obj}',
                content_object=obj,
                assigned_to=user,
                created_by=user,
                due_date=timezone.now() + timedelta(days=random.randint(1, 30)),
                priority=random.choice(priorities),
                target_status=target_status,
                project=project
            )

    def _create_samples(self, individual, sample_types, test_types, analysis_types, num_samples, tests_per_sample, analyses_per_test, tasks_per_object, user, statuses, project):
        for i in range(num_samples):
            # Create sample
            sample = Sample.objects.create(
                individual=individual,
                sample_type=random.choice(sample_types),
                status=statuses['registered'],
                receipt_date=timezone.now() - timedelta(days=random.randint(1, 30)),
                isolation_by=user,
                created_by=user
            )

            # Create tasks for sample
            self._create_tasks(sample, user, statuses['completed'], project, tasks_per_object)

            # Create tests for sample
            for j in range(tests_per_sample):
                test = Test.objects.create(
                    test_type=random.choice(test_types),
                    performed_date=timezone.now() - timedelta(days=random.randint(1, 15)),
                    performed_by=user,
                    sample=sample,
                    created_by=user,
                    status=statuses['active']
                )

                # Create tasks for test
                self._create_tasks(test, user, statuses['completed'], project, tasks_per_object)

                # Create analyses for test
                for k in range(analyses_per_test):
                    analysis = Analysis.objects.create(
                        test=test,
                        performed_date=timezone.now() - timedelta(days=random.randint(1, 10)),
                        performed_by=user,
                        type=random.choice(analysis_types),
                        status=statuses['active'],
                        created_by=user
                    )

                    # Create tasks for analysis
                    self._create_tasks(analysis, user, statuses['completed'], project, tasks_per_object)

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
            CrossIdentifier.objects.create(
                individual=individual,
                id_type=identifier_types[0],
                id_value=lab_id,
                link=f"https://www.rareboost.com/individual/{lab_id}",
                created_by=user
            )
            CrossIdentifier.objects.create(
                individual=individual,
                id_type=identifier_types[1],
                id_value=biobank_id,
                link=f"https://www.biobank.com/individual/{biobank_id}",
                created_by=user
            )
            CrossIdentifier.objects.create(
                individual=individual,
                id_type=identifier_types[2],
                id_value=random.randint(1000000000, 9999999999),
                link=f"https://www.erdera.com/individual/{random.randint(1000000000, 9999999999)}",
                created_by=user
            )