import os
import django
import random
from datetime import datetime, timedelta

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rareindex.settings')
django.setup()

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from lab.models import (
    SampleType, TestType, AnalysisType, Status,
    Individual, Sample, Test, Analysis, Institution
)

def create_sample_data():
    # Get or create a user for created_by fields
    user = User.objects.first()
    if not user:
        user = User.objects.create_superuser('admin', 'admin@example.com', 'admin')

    # Get content types for our models
    individual_ct = ContentType.objects.get_for_model(Individual)
    sample_ct = ContentType.objects.get_for_model(Sample)
    test_ct = ContentType.objects.get_for_model(Test)
    analysis_ct = ContentType.objects.get_for_model(Analysis)

    # Create an Institution
    institution, _ = Institution.objects.get_or_create(
        name="Test Hospital",
        defaults={
            'created_by': user
        }
    )

    # Create Sample Types
    sample_types_data = [
        ("Blood", "Whole blood sample"),
        ("Tissue", "Tissue biopsy sample"),
        ("Saliva", "Saliva sample for DNA extraction"),
        ("Urine", "Urine sample for metabolic analysis"),
        ("CSF", "Cerebrospinal fluid sample"),
        ("Plasma", "Blood plasma sample"),
    ]

    sample_types = []
    for name, desc in sample_types_data:
        st, _ = SampleType.objects.get_or_create(
            name=name,
            defaults={
                'description': desc,
                'created_by': user
            }
        )
        sample_types.append(st)

    # Create Test Types
    test_types_data = [
        ("Whole Genome Sequencing", "Complete genome sequencing analysis"),
        ("Exome Sequencing", "Targeted exome sequencing"),
        ("RNA Sequencing", "Transcriptome analysis"),
        ("Metabolomics", "Comprehensive metabolite analysis"),
        ("Proteomics", "Protein expression analysis"),
        ("Methylation Analysis", "DNA methylation profiling"),
        ("Panel Sequencing", "Targeted gene panel analysis"),
    ]

    test_types = []
    for name, desc in test_types_data:
        tt, _ = TestType.objects.get_or_create(
            name=name,
            defaults={
                'description': desc,
                'created_by': user
            }
        )
        test_types.append(tt)

    # Create Analysis Types
    analysis_types_data = [
        ("Quality Control", "Initial quality assessment"),
        ("Variant Calling", "Identification of genetic variants"),
        ("Expression Analysis", "Gene expression quantification"),
        ("Pathway Analysis", "Biological pathway analysis"),
    ]

    analysis_types = []
    for name, desc in analysis_types_data:
        at, _ = AnalysisType.objects.get_or_create(
            name=name,
            defaults={
                'description': desc,
                'created_by': user
            }
        )
        analysis_types.append(at)

    # Create Statuses for each model type
    status_data = {
        'individual': [
            ("Registered", "Individual has been registered in the system", "#6B7280", individual_ct),  # gray
            ("Active", "Individual is actively participating", "#059669", individual_ct),  # green
            ("Completed", "All planned tests completed", "#0284C7", individual_ct),  # blue
            ("Withdrawn", "Individual has withdrawn from the study", "#DC2626", individual_ct),  # red
        ],
        'sample': [
            ("Received", "Sample has been received", "#6B7280", sample_ct),  # gray
            ("In Storage", "Sample is properly stored", "#059669", sample_ct),  # green
            ("In Processing", "Sample is being processed", "#0284C7", sample_ct),  # blue
            ("Depleted", "Sample has been depleted", "#DC2626", sample_ct),  # red
            ("Quality Control", "Sample is undergoing QC", "#7C3AED", sample_ct),  # purple
        ],
        'test': [
            ("Scheduled", "Test has been scheduled", "#6B7280", test_ct),  # gray
            ("In Progress", "Test is being performed", "#0284C7", test_ct),  # blue
            ("Completed", "Test has been completed", "#059669", test_ct),  # green
            ("Failed", "Test has failed", "#DC2626", test_ct),  # red
            ("On Hold", "Test is temporarily suspended", "#F59E0B", test_ct),  # amber
        ],
        'analysis': [
            ("Queued", "Analysis is in the queue", "#6B7280", analysis_ct),  # gray
            ("Processing", "Analysis is being processed", "#0284C7", analysis_ct),  # blue
            ("Completed", "Analysis has been completed", "#059669", analysis_ct),  # green
            ("Failed", "Analysis has failed", "#DC2626", analysis_ct),  # red
            ("Under Review", "Results are being reviewed", "#7C3AED", analysis_ct),  # purple
        ]
    }

    statuses = {model_type: [] for model_type in status_data.keys()}
    
    for model_type, model_statuses in status_data.items():
        for name, desc, color, content_type in model_statuses:
            status, _ = Status.objects.get_or_create(
                name=name,
                content_type=content_type,
                defaults={
                    'description': desc,
                    'color': color,
                    'created_by': user
                }
            )
            statuses[model_type].append(status)

    # Create Individuals (10)
    individuals = []
    for i in range(1, 11):
        ind, _ = Individual.objects.get_or_create(
            lab_id=f"IND{i:03d}",
            defaults={
                'created_by': user,
                'status': random.choice(statuses['individual'])
            }
        )
        individuals.append(ind)

    # Create Samples (2-3 per individual)
    samples = []
    for individual in individuals:
        num_samples = random.randint(2, 3)
        for _ in range(num_samples):
            sample = Sample.objects.create(
                individual=individual,
                sample_type=random.choice(sample_types),
                status=random.choice(statuses['sample']),
                receipt_date=datetime.now().date() - timedelta(days=random.randint(0, 30)),
                created_by=user,
                sending_institution=institution,
                isolation_by=user
            )
            samples.append(sample)

    # Create Tests (2-4 per sample)
    tests = []
    for sample in samples:
        num_tests = random.randint(2, 4)
        for _ in range(num_tests):
            test = Test.objects.create(
                sample=sample,
                test_type=random.choice(test_types),
                status=random.choice(statuses['test']),
                performed_date=datetime.now().date() - timedelta(days=random.randint(0, 15)),
                created_by=user,
                performed_by=user
            )
            tests.append(test)

    # Create Analyses (2-3 per test)
    for test in tests:
        num_analyses = random.randint(2, 3)
        for _ in range(num_analyses):
            Analysis.objects.create(
                test=test,
                type=random.choice(analysis_types),
                status=random.choice(statuses['analysis']),
                created_by=user,
                performed_date=datetime.now().date() - timedelta(days=random.randint(0, 15)),
                performed_by=user
            )

    # Print summary
    print(f"Created:")
    print(f"- {len(sample_types)} Sample Types")
    print(f"- {len(test_types)} Test Types")
    print(f"- {len(analysis_types)} Analysis Types")
    print(f"- {sum(len(s) for s in statuses.values())} Statuses:")
    for model_type, model_statuses in statuses.items():
        print(f"  - {len(model_statuses)} {model_type.title()} statuses")
    print(f"- {len(individuals)} Individuals")
    print(f"- {len(samples)} Samples")
    print(f"- {len(tests)} Tests")
    print(f"- {Analysis.objects.count()} Analyses")

if __name__ == '__main__':
    create_sample_data() 