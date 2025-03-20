from django.core.management.base import BaseCommand
import random
from datetime import datetime, timedelta
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from lab.models import (
    SampleType,
    TestType,
    AnalysisType,
    Status,
    Individual,
    Sample,
    Test,
    Analysis,
    Institution,
)


class Command(BaseCommand):
    help = "Generates test data for the lab application including individuals, samples, tests, and analyses"

    def handle(self, *args, **options):
        # Get or create a user for created_by fields
        user = User.objects.first()
        if not user:
            user = User.objects.create_superuser("admin", "admin@example.com", "admin")

        # Get content types for our models
        individual_ct = ContentType.objects.get_for_model(Individual)
        sample_ct = ContentType.objects.get_for_model(Sample)
        test_ct = ContentType.objects.get_for_model(Test)
        analysis_ct = ContentType.objects.get_for_model(Analysis)

        # Create an Institution
        institution, _ = Institution.objects.get_or_create(
            name="Test Hospital", defaults={"created_by": user}
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
                name=name, defaults={"description": desc, "created_by": user}
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
                name=name, defaults={"description": desc, "created_by": user}
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
                name=name, defaults={"description": desc, "created_by": user}
            )
            analysis_types.append(at)

        # Create Statuses for each model type
        status_data = {
            "individual": [
                (
                    "Registered",
                    "Individual has been registered in the system",
                    "#6B7280",
                    individual_ct,
                ),  # gray
                (
                    "Active",
                    "Individual is actively participating",
                    "#059669",
                    individual_ct,
                ),  # green
                (
                    "Completed",
                    "All planned tests completed",
                    "#0284C7",
                    individual_ct,
                ),  # blue
                (
                    "Withdrawn",
                    "Individual has withdrawn from the study",
                    "#DC2626",
                    individual_ct,
                ),  # red
            ],
            "sample": [
                ("Received", "Sample has been received", "#6B7280", sample_ct),  # gray
                (
                    "In Storage",
                    "Sample is properly stored",
                    "#059669",
                    sample_ct,
                ),  # green
                (
                    "In Processing",
                    "Sample is being processed",
                    "#0284C7",
                    sample_ct,
                ),  # blue
                ("Depleted", "Sample has been depleted", "#DC2626", sample_ct),  # red
                (
                    "Quality Control",
                    "Sample is undergoing QC",
                    "#7C3AED",
                    sample_ct,
                ),  # purple
            ],
            "test": [
                ("Scheduled", "Test has been scheduled", "#6B7280", test_ct),  # gray
                ("In Progress", "Test is being performed", "#0284C7", test_ct),  # blue
                ("Completed", "Test has been completed", "#059669", test_ct),  # green
                ("Failed", "Test has failed", "#DC2626", test_ct),  # red
                (
                    "On Hold",
                    "Test is temporarily suspended",
                    "#F59E0B",
                    test_ct,
                ),  # amber
            ],
            "analysis": [
                ("Queued", "Analysis is in the queue", "#6B7280", analysis_ct),  # gray
                (
                    "Processing",
                    "Analysis is being processed",
                    "#0284C7",
                    analysis_ct,
                ),  # blue
                (
                    "Completed",
                    "Analysis has been completed",
                    "#059669",
                    analysis_ct,
                ),  # green
                ("Failed", "Analysis has failed", "#DC2626", analysis_ct),  # red
                (
                    "Under Review",
                    "Results are being reviewed",
                    "#7C3AED",
                    analysis_ct,
                ),  # purple
            ],
        }

        statuses = {model_type: [] for model_type in status_data.keys()}

        for model_type, model_statuses in status_data.items():
            for name, desc, color, content_type in model_statuses:
                status, _ = Status.objects.get_or_create(
                    name=name,
                    content_type=content_type,
                    defaults={"description": desc, "color": color, "created_by": user},
                )
                statuses[model_type].append(status)

        # Create Individuals (10)
        individuals = []
        # First create all individuals without relationships
        for i in range(1, 11):
            ind, _ = Individual.objects.get_or_create(
                lab_id=f"IND{i:03d}",
                defaults={
                    "biobank_id": f"BIO{i:03d}",
                    "full_name": f"Test Person {i}",
                    "created_by": user,
                    "status": random.choice(statuses["individual"]),
                },
            )
            individuals.append(ind)

        # Now create family relationships
        # We'll create two family groups: 0-4 and 5-9
        # Family 1: IND001 and IND002 are parents, IND003 and IND004 are their children
        individuals[2].mother = individuals[1]  # IND003's mother is IND002
        individuals[2].father = individuals[0]  # IND003's father is IND001
        individuals[3].mother = individuals[1]  # IND004's mother is IND002
        individuals[3].father = individuals[0]  # IND004's father is IND001
        individuals[2].save()
        individuals[3].save()

        # Family 2: IND006 and IND007 are parents, IND008 and IND009 are their children
        individuals[7].mother = individuals[6]  # IND008's mother is IND007
        individuals[7].father = individuals[5]  # IND008's father is IND006
        individuals[8].mother = individuals[6]  # IND009's mother is IND007
        individuals[8].father = individuals[5]  # IND009's father is IND006
        individuals[7].save()
        individuals[8].save()

        # IND005 and IND010 remain without parents as controls

        # Create Samples (2-3 per individual)
        samples = []
        for individual in individuals:
            num_samples = random.randint(2, 3)
            for _ in range(num_samples):
                sample = Sample.objects.create(
                    individual=individual,
                    sample_type=random.choice(sample_types),
                    status=random.choice(statuses["sample"]),
                    receipt_date=datetime.now().date()
                    - timedelta(days=random.randint(0, 30)),
                    created_by=user,
                    sending_institution=institution,
                    isolation_by=user,
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
                    status=random.choice(statuses["test"]),
                    performed_date=datetime.now().date()
                    - timedelta(days=random.randint(0, 15)),
                    created_by=user,
                    performed_by=user,
                )
                tests.append(test)

        # Create Analyses (2-3 per test)
        for test in tests:
            num_analyses = random.randint(2, 3)
            for _ in range(num_analyses):
                Analysis.objects.create(
                    test=test,
                    type=random.choice(analysis_types),
                    status=random.choice(statuses["analysis"]),
                    created_by=user,
                    performed_date=datetime.now().date()
                    - timedelta(days=random.randint(0, 15)),
                    performed_by=user,
                )

        # Print summary
        self.stdout.write(self.style.SUCCESS(f"Created:"))
        self.stdout.write(self.style.SUCCESS(f"- {len(sample_types)} Sample Types"))
        self.stdout.write(self.style.SUCCESS(f"- {len(test_types)} Test Types"))
        self.stdout.write(self.style.SUCCESS(f"- {len(analysis_types)} Analysis Types"))
        self.stdout.write(
            self.style.SUCCESS(f"- {sum(len(s) for s in statuses.values())} Statuses:")
        )
        for model_type, model_statuses in statuses.items():
            self.stdout.write(
                self.style.SUCCESS(
                    f"  - {len(model_statuses)} {model_type.title()} statuses"
                )
            )
        self.stdout.write(self.style.SUCCESS(f"- {len(individuals)} Individuals"))
        self.stdout.write(self.style.SUCCESS(f"- {len(samples)} Samples"))
        self.stdout.write(self.style.SUCCESS(f"- {len(tests)} Tests"))
        self.stdout.write(self.style.SUCCESS(f"- {Analysis.objects.count()} Analyses"))
