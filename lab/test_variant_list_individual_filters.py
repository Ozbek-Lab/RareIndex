from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from lab.filters import VariantFilter
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
    Status,
    Test,
    TestType,
)
from variant.models import Gene, SNV, Variant
from variant.signals import annotate_and_link_genes


class VariantListIndividualFilterTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        post_save.disconnect(annotate_and_link_genes, sender=SNV)

    @classmethod
    def tearDownClass(cls):
        post_save.connect(annotate_and_link_genes, sender=SNV)
        super().tearDownClass()

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="variant-list-filter-user",
            password="password",
        )
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Variant),
                codename="view_variant",
            )
        )
        self.client.login(username="variant-list-filter-user", password="password")

        self.first_individual = Individual.objects.create(
            full_name="First",
            sex="female",
            is_affected=True,
            created_by=self.user,
        )
        self.second_individual = Individual.objects.create(
            full_name="Second",
            sex="male",
            is_affected=False,
            created_by=self.user,
        )
        self.project = Project.objects.create(name="Variant Project", created_by=self.user)
        self.project.individuals.add(self.first_individual, self.second_individual)
        ProjectMembership.objects.create(
            project=self.project,
            user=self.user,
            role=ProjectMembership.Role.VIEWER,
            created_by=self.user,
        )
        self.first_variant = SNV.objects.create(
            assembly_version="hg38",
            chromosome="chr1",
            start=100,
            end=100,
            individual=self.first_individual,
            created_by=self.user,
            zygosity="het",
            reference="A",
            alternate="G",
        )
        self.second_variant = SNV.objects.create(
            assembly_version="hg38",
            chromosome="chr2",
            start=200,
            end=200,
            individual=self.second_individual,
            created_by=self.user,
            zygosity="hom",
            reference="C",
            alternate="T",
        )

        gene = Gene.objects.create(
            hgnc_id="HGNC:2",
            symbol="GENE2",
            name="Gene Two",
        )
        self.second_variant.genes.add(gene)

        blood = SampleType.objects.create(name="Blood", created_by=self.user)
        tissue = SampleType.objects.create(name="Tissue", created_by=self.user)
        self.first_blood_sample = Sample.objects.create(
            individual=self.first_individual,
            sample_type=blood,
            created_by=self.user,
        )
        self.first_tissue_sample = Sample.objects.create(
            individual=self.first_individual,
            sample_type=tissue,
            created_by=self.user,
        )
        self.second_blood_sample = Sample.objects.create(
            individual=self.second_individual,
            sample_type=blood,
            created_by=self.user,
        )

        sample_ct = ContentType.objects.get_for_model(Sample)
        self.received_status = Status.objects.create(
            name="Received",
            content_type=sample_ct,
            created_by=self.user,
        )
        self.first_tissue_sample.statuses.add(self.received_status)
        self.second_blood_sample.statuses.add(self.received_status)

        individual_ct = ContentType.objects.get_for_model(Individual)
        self.solved_status = Status.objects.create(
            name="Solved",
            content_type=individual_ct,
            created_by=self.user,
        )
        self.first_individual.statuses.add(self.solved_status)

        test_type = TestType.objects.create(name="Genome", created_by=self.user)
        test = Test.objects.create(
            sample=self.second_blood_sample,
            test_type=test_type,
            created_by=self.user,
        )
        pipeline_type = PipelineType.objects.create(
            name="Short Reads",
            created_by=self.user,
        )
        pipeline = Pipeline.objects.create(
            test=test,
            type=pipeline_type,
            performed_by=self.user,
            performed_date=timezone.now().date(),
            created_by=self.user,
        )
        analysis_type = AnalysisType.objects.create(
            name="Diagnostic",
            created_by=self.user,
        )
        self.analysis = Analysis.objects.create(
            pipeline=pipeline,
            type=analysis_type,
            created_by=self.user,
        )

    def assert_variant_ids(self, data, expected_ids):
        filterset = VariantFilter(data=data, queryset=Variant.objects.all())
        self.assertTrue(filterset.form.is_valid(), filterset.form.errors)
        self.assertEqual(set(filterset.qs.values_list("pk", flat=True)), expected_ids)

    def test_filters_variants_by_individual_fields(self):
        self.assert_variant_ids({"sex": ["female"]}, {self.first_variant.pk})
        self.assert_variant_ids({"is_affected": ["True"]}, {self.first_variant.pk})

    def test_filters_variants_by_individual_status(self):
        self.assert_variant_ids(
            {"individual_status": ["Solved"]},
            {self.first_variant.pk},
        )

    def test_exclude_only_individual_filter_is_applied(self):
        self.assert_variant_ids(
            {"individual_status__exclude": ["Solved"]},
            {self.second_variant.pk},
        )

    def test_together_mode_keeps_sample_filters_on_same_sample(self):
        data = {
            "samples__sample_type": ["Blood"],
            "samples__status": ["Received"],
            "samples__status__mode": "together",
        }

        self.assert_variant_ids(data, {self.second_variant.pk})

    def test_any_group_mode_combines_variant_and_individual_filters(self):
        data = {
            "filter_group_mode": "any",
            "sex": ["female"],
            "gene": "GENE2",
        }

        self.assert_variant_ids(data, {self.first_variant.pk, self.second_variant.pk})

    def test_variant_sidebar_renders_variant_and_annotation_sections_first(self):
        response = self.client.get(reverse("lab:variant_list"), follow=True)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertLess(
            content.index("<span>Variant</span>"),
            content.index("<span>Annotations</span>"),
        )
        self.assertLess(
            content.index("<span>Annotations</span>"),
            content.index("<span>Individual</span>"),
        )
