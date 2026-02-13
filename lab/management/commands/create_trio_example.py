import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
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
    IdentifierType,
    CrossIdentifier,
    Analysis,
    AnalysisType,
    AnalysisReport
)
from variant.models import SNV, Classification

class Command(BaseCommand):
    help = 'Create an example trio family with samples, tests, pipelines, analysis, variant, and report'

    def handle(self, *args, **options):
        # 1. Preparation: Get/Create support data
        user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if not user:
            self.stdout.write(self.style.ERROR('No user found. Please create a user first.'))
            return

        institution, _ = Institution.objects.get_or_create(
            name="Rare Disease Lab",
            defaults={'created_by': user}
        )

        # Statuses
        ind_ct = ContentType.objects.get_for_model(Individual)
        smp_ct = ContentType.objects.get_for_model(Sample)
        tst_ct = ContentType.objects.get_for_model(Test)
        pip_ct = ContentType.objects.get_for_model(Pipeline)

        registered_status, _ = Status.objects.get_or_create(
            name='Registered', content_type=ind_ct, defaults={'color': 'gray', 'created_by': user}
        )
        active_status, _ = Status.objects.get_or_create(
            name='Active', content_type=ind_ct, defaults={'color': 'green', 'created_by': user}
        )
        smp_active, _ = Status.objects.get_or_create(
            name='Active', content_type=smp_ct, defaults={'color': 'green', 'created_by': user}
        )
        tst_active, _ = Status.objects.get_or_create(
            name='Active', content_type=tst_ct, defaults={'color': 'green', 'created_by': user}
        )
        pip_completed, _ = Status.objects.get_or_create(
            name='Completed', content_type=pip_ct, defaults={'color': 'blue', 'created_by': user}
        )

        # Types
        blood_type, _ = SampleType.objects.get_or_create(name='Whole Blood', defaults={'created_by': user})
        wgs_type, _ = TestType.objects.get_or_create(name='WGS', defaults={'created_by': user})
        rarepipe_type, _ = PipelineType.objects.get_or_create(
            name='rarepipe', version='1.0', defaults={'created_by': user}
        )
        initial_analysis_type, _ = AnalysisType.objects.get_or_create(
            name='Initial', defaults={'created_by': user}
        )
        
        rb_id_type, _ = IdentifierType.objects.get_or_create(
            name='RareBoost', defaults={'created_by': user}
        )

        # 2. Family Creation
        family_id = "FAM_TRIO_EXAMPLE_001"
        if Family.objects.filter(family_id=family_id).exists():
            self.stdout.write(self.style.WARNING(f'Family {family_id} already exists. Cleaning up related records to recreate.'))
            fam = Family.objects.get(family_id=family_id)
            inds = Individual.objects.filter(family=fam)
            
            # Delete in order of dependency
            for ind in inds:
                # Samples -> Tests -> Pipelines -> Variants/Reports/Analyses
                samples = Sample.objects.filter(individual=ind)
                for sample in samples:
                    tests = Test.objects.filter(sample=sample)
                    for test in tests:
                        pips = Pipeline.objects.filter(test=test)
                        for pip in pips:
                            SNV.objects.filter(pipeline=pip).delete()
                            AnalysisReport.objects.filter(pipeline=pip).delete()
                            Analysis.objects.filter(pipeline=pip).delete()
                        pips.delete()
                    tests.delete()
                samples.delete()
                CrossIdentifier.objects.filter(individual=ind).delete()
            
            # Now delete individuals (children first)
            inds.filter(is_index=True).delete()
            inds.delete()
            fam.delete()

        family = Family.objects.create(
            family_id=family_id,
            description="Example trio family for demonstration",
            created_by=user
        )

        # 3. Individual Creation
        mother = Individual.objects.create(
            full_name=f"Mother TRIO_001",
            family=family,
            sex='female',
            status=registered_status,
            created_by=user
        )
        mother.institution.add(institution)
        
        father = Individual.objects.create(
            full_name=f"Father TRIO_001",
            family=family,
            sex='male',
            status=registered_status,
            created_by=user
        )
        father.institution.add(institution)

        proband = Individual.objects.create(
            full_name=f"Proband TRIO_001",
            family=family,
            mother=mother,
            father=father,
            is_index=True,
            sex='male',
            status=active_status,
            created_by=user
        )
        proband.institution.add(institution)

        # Identifiers
        CrossIdentifier.objects.create(individual=mother, id_type=rb_id_type, id_value=f"{family_id}.2", created_by=user)
        CrossIdentifier.objects.create(individual=father, id_type=rb_id_type, id_value=f"{family_id}.3", created_by=user)
        CrossIdentifier.objects.create(individual=proband, id_type=rb_id_type, id_value=f"{family_id}.1", created_by=user)

        # 4. Workflow for everyone
        for ind in [mother, father, proband]:
            sample = Sample.objects.create(
                individual=ind,
                sample_type=blood_type,
                status=smp_active,
                receipt_date=timezone.now().date(),
                created_by=user,
                isolation_by=user
            )
            test = Test.objects.create(
                sample=sample,
                test_type=wgs_type,
                status=tst_active,
                created_by=user,
                performed_date=timezone.now().date(),
                performed_by=user
            )
            pipeline = Pipeline.objects.create(
                test=test,
                type=rarepipe_type,
                status=pip_completed,
                created_by=user,
                performed_date=timezone.now().date(),
                performed_by=user
            )

            if ind == proband:
                # 5. Proband Specifics
                analysis = Analysis.objects.create(
                    pipeline=pipeline,
                    analysis_type=initial_analysis_type,
                    created_by=user
                )

                variant = SNV.objects.create(
                    individual=ind,
                    pipeline=pipeline,
                    chromosome="chr1",
                    start=123456,
                    end=123457,
                    reference="A",
                    alternate="G",
                    zygosity="het",
                    created_by=user
                )

                Classification.objects.create(
                    variant=variant,
                    user=user,
                    classification='pathogenic',
                    inheritance='de_novo',
                    notes="Example pathogenic variant"
                )

                report = AnalysisReport.objects.create(
                    pipeline=pipeline,
                    description="Example clinical report for Proband",
                    created_by=user
                )
                report.variants.add(variant)
                
                # Mock PDF file
                dummy_content = b"%PDF-1.4\n1 0 obj\n<< /Title (Example Report) >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
                report.file.save(
                    f"{family_id}_proband_report.pdf",
                    ContentFile(dummy_content)
                )

        self.stdout.write(self.style.SUCCESS(f'Successfully created trio family {family_id}'))

