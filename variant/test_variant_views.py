from datetime import date

from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from lab.models import (
    Analysis,
    AnalysisType,
    Individual,
    Pipeline,
    PipelineType,
    Project,
    ProjectMembership,
    Sample,
    SampleType,
    Test,
    TestType,
)
from variant.models import SNV, Variant, delins
from variant.signals import annotate_and_link_genes


@override_settings(
    SECURE_SSL_REDIRECT=False,
    MIDDLEWARE=[
        middleware
        for middleware in settings.MIDDLEWARE
        if middleware != "reversion.middleware.RevisionMiddleware"
    ],
)
class VariantCreateViewTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for sender in (SNV, delins):
            post_save.disconnect(annotate_and_link_genes, sender=sender)

    @classmethod
    def tearDownClass(cls):
        for sender in (SNV, delins):
            post_save.connect(annotate_and_link_genes, sender=sender)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(
            username="variant-create-user",
            password="password",
        )
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Variant),
                codename="add_variant",
            )
        )
        self.client.force_login(self.user)

        self.project = Project.objects.create(
            name="Variant Create Project",
            created_by=self.user,
        )
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ProjectMembership.Role.EDITOR,
            created_by=self.user,
        )
        self.individual = Individual.objects.create(
            full_name="Variant Create Person",
            created_by=self.user,
        )
        self.project.individuals.add(self.individual)

        sample_type = SampleType.objects.create(name="Blood", created_by=self.user)
        test_type = TestType.objects.create(name="WGS", created_by=self.user)
        pipeline_type = PipelineType.objects.create(
            name="GATK",
            version="4.0",
            created_by=self.user,
        )
        analysis_type = AnalysisType.objects.create(
            name="Diagnostic",
            created_by=self.user,
        )
        self.sample = Sample.objects.create(
            individual=self.individual,
            sample_type=sample_type,
            created_by=self.user,
        )
        self.test = Test.objects.create(
            sample=self.sample,
            test_type=test_type,
            created_by=self.user,
        )
        self.pipeline = Pipeline.objects.create(
            test=self.test,
            type=pipeline_type,
            performed_by=self.user,
            performed_date=date(2026, 8, 31),
            created_by=self.user,
        )
        self.analysis = Analysis.objects.create(
            pipeline=self.pipeline,
            type=analysis_type,
            created_by=self.user,
        )

    def test_variant_create_with_analysis_id_links_variant_to_analysis(self):
        response = self.client.post(
            f"{reverse('lab:variant_create')}?analysis_id={self.analysis.pk}&type=delins",
            {
                "assembly_version": "hg38",
                "delins_string": "chr3:33114394TGC>T",
                "zygosity": "het",
            },
        )

        self.assertEqual(response.status_code, 302)
        variant = delins.objects.get()
        self.assertEqual(variant.individual, self.individual)
        self.assertEqual(variant.analysis, self.analysis)
        self.assertEqual(variant.chromosome, "chr3")
        self.assertEqual(variant.start, 33114394)
        self.assertEqual(variant.end, 33114394)
        self.assertEqual(variant.reference, "TGC")
        self.assertEqual(variant.alternate, "T")
        self.assertIn(reverse("lab:generic_detail"), response["Location"])
        self.assertIn("model_name=Analysis", response["Location"])

    def test_variant_create_with_pipeline_id_still_creates_direct_variant(self):
        response = self.client.post(
            f"{reverse('lab:variant_create')}?pipeline_id={self.pipeline.pk}&type=snv",
            {
                "assembly_version": "hg38",
                "snv_string": "chr10:77984023A>G",
                "zygosity": "hom",
            },
        )

        self.assertEqual(response.status_code, 302)
        variant = SNV.objects.get()
        self.assertEqual(variant.individual, self.individual)
        self.assertIsNone(variant.analysis)
        self.assertEqual(variant.chromosome, "chr10")
        self.assertEqual(variant.start, 77984023)
        self.assertEqual(variant.end, 77984023)
        self.assertEqual(variant.reference, "A")
        self.assertEqual(variant.alternate, "G")
        self.assertIn(reverse("lab:generic_detail"), response["Location"])
        self.assertIn("model_name=Pipeline", response["Location"])
