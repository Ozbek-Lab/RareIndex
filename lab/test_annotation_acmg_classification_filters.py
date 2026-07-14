from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.test import TestCase

from lab.filters import IndividualFilter, VariantFilter
from lab.models import Individual
from variant.models import Annotation, SNV, Variant
from variant.signals import annotate_and_link_genes


class AnnotationACMGClassificationFilterTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        post_save.disconnect(annotate_and_link_genes, sender=SNV)

    @classmethod
    def tearDownClass(cls):
        post_save.connect(annotate_and_link_genes, sender=SNV)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(username="annotation-acmg-filter-user")
        self.first_individual = Individual.objects.create(
            full_name="First",
            created_by=self.user,
        )
        self.second_individual = Individual.objects.create(
            full_name="Second",
            created_by=self.user,
        )

        self.uncertain_variant = SNV.objects.create(
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
        Annotation.objects.create(
            variant=self.uncertain_variant,
            source="genebe",
            data={"variants": [{"acmg_classification": "Uncertain_significance"}]},
        )

        self.benign_variant = SNV.objects.create(
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
        Annotation.objects.create(
            variant=self.benign_variant,
            source="genebe",
            data={"variants": [{"acmg_classification": "Benign"}]},
        )

        self.non_genebe_variant = SNV.objects.create(
            assembly_version="hg38",
            chromosome="chr3",
            start=300,
            end=300,
            individual=self.second_individual,
            created_by=self.user,
            zygosity="het",
            reference="G",
            alternate="A",
        )
        Annotation.objects.create(
            variant=self.non_genebe_variant,
            source="other",
            data={"variants": [{"acmg_classification": "Uncertain_significance"}]},
        )

    def test_filter_choices_include_parsed_genebe_annotation_acmg_classifications(self):
        variant_filter = VariantFilter(queryset=Variant.objects.all())
        individual_filter = IndividualFilter(queryset=Individual.objects.all())

        self.assertIn(
            ("Uncertain_significance", "Uncertain Significance"),
            list(variant_filter.form.fields["annotation_acmg_classification"].choices),
        )
        self.assertIn(
            ("Uncertain_significance", "Uncertain Significance"),
            list(individual_filter.form.fields["variants__annotation_acmg_classification"].choices),
        )

    def test_variant_filter_matches_genebe_annotation_acmg_classification(self):
        filterset = VariantFilter(
            data={"annotation_acmg_classification": ["Uncertain_significance"]},
            queryset=Variant.objects.all(),
        )

        self.assertEqual(
            set(filterset.qs.values_list("pk", flat=True)),
            {self.uncertain_variant.pk},
        )

    def test_variant_filter_excludes_genebe_annotation_acmg_classification(self):
        filterset = VariantFilter(
            data={"annotation_acmg_classification__exclude": ["Uncertain_significance"]},
            queryset=Variant.objects.all(),
        )

        variant_ids = set(filterset.qs.values_list("pk", flat=True))
        self.assertNotIn(self.uncertain_variant.pk, variant_ids)
        self.assertIn(self.benign_variant.pk, variant_ids)
        self.assertIn(self.non_genebe_variant.pk, variant_ids)

    def test_individual_filter_matches_variant_annotation_acmg_classification(self):
        filterset = IndividualFilter(
            data={"variants__annotation_acmg_classification": ["Uncertain_significance"]},
            queryset=Individual.objects.all(),
        )

        self.assertEqual(
            set(filterset.qs.values_list("pk", flat=True)),
            {self.first_individual.pk},
        )
