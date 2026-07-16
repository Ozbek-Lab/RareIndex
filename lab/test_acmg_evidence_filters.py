from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.test import TestCase

from lab.filters import IndividualFilter, VariantFilter
from lab.models import Individual
from variant.models import ACMGEvidenceOverride, CNV, SNV, Variant
from variant.signals import annotate_and_link_genes


class ACMGEvidenceFilterTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        post_save.disconnect(annotate_and_link_genes, sender=SNV)
        post_save.disconnect(annotate_and_link_genes, sender=CNV)

    @classmethod
    def tearDownClass(cls):
        post_save.connect(annotate_and_link_genes, sender=SNV)
        post_save.connect(annotate_and_link_genes, sender=CNV)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(username="acmg-evidence-filter-user")
        self.first_individual = Individual.objects.create(
            full_name="First",
            created_by=self.user,
        )
        self.second_individual = Individual.objects.create(
            full_name="Second",
            created_by=self.user,
        )

        self.pm2_snv = SNV.objects.create(
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
        ACMGEvidenceOverride.objects.create(
            variant=self.pm2_snv,
            criterion="PM2",
            source="genebe",
            included=True,
        )

        self.pvs1_cnv = CNV.objects.create(
            assembly_version="hg38",
            chromosome="chr2",
            start=200,
            end=300,
            individual=self.first_individual,
            created_by=self.user,
            zygosity="het",
            cnv_type="loss",
        )
        ACMGEvidenceOverride.objects.create(
            variant=self.pvs1_cnv,
            criterion="PVS1",
            source="manual",
            included=True,
        )

        self.pvs1_snv = SNV.objects.create(
            assembly_version="hg38",
            chromosome="chr3",
            start=400,
            end=400,
            individual=self.second_individual,
            created_by=self.user,
            zygosity="hom",
            reference="C",
            alternate="T",
        )
        ACMGEvidenceOverride.objects.create(
            variant=self.pvs1_snv,
            criterion="PVS1",
            source="genebe",
            included=True,
        )
        ACMGEvidenceOverride.objects.create(
            variant=self.pvs1_snv,
            criterion="BP4",
            source="manual",
            included=False,
        )

    def test_variant_filter_matches_included_acmg_evidence(self):
        filterset = VariantFilter(
            data={"acmg_evidence": ["PVS1"]},
            queryset=Variant.objects.all(),
        )

        self.assertEqual(
            set(filterset.qs.values_list("pk", flat=True)),
            {self.pvs1_cnv.pk, self.pvs1_snv.pk},
        )

    def test_variant_filter_excludes_included_acmg_evidence(self):
        filterset = VariantFilter(
            data={"acmg_evidence__exclude": ["PM2"]},
            queryset=Variant.objects.all(),
        )

        variant_ids = set(filterset.qs.values_list("pk", flat=True))
        self.assertNotIn(self.pm2_snv.pk, variant_ids)
        self.assertIn(self.pvs1_snv.pk, variant_ids)

    def test_excluded_or_inactive_evidence_does_not_match(self):
        filterset = VariantFilter(
            data={"acmg_evidence": ["BP4"]},
            queryset=Variant.objects.all(),
        )

        self.assertEqual(set(filterset.qs.values_list("pk", flat=True)), set())

    def test_individual_filter_matches_variant_acmg_evidence(self):
        filterset = IndividualFilter(
            data={"variants__acmg_evidence": ["PVS1"]},
            queryset=Individual.objects.all(),
        )

        self.assertEqual(
            set(filterset.qs.values_list("pk", flat=True)),
            {self.first_individual.pk, self.second_individual.pk},
        )

    def test_individual_variant_together_mode_keeps_evidence_on_same_variant(self):
        data = {
            "variant_type": ["SNV"],
            "variants__acmg_evidence": ["PVS1"],
            "variants__acmg_evidence__mode": "together",
        }
        filterset = IndividualFilter(data=data, queryset=Individual.objects.all())

        self.assertEqual(
            set(filterset.qs.values_list("pk", flat=True)),
            {self.second_individual.pk},
        )

    def test_individual_any_group_mode_can_exclude_acmg_evidence(self):
        data = {
            "filter_group_mode": "any",
            "variants__acmg_evidence__exclude": ["PM2"],
        }
        filterset = IndividualFilter(data=data, queryset=Individual.objects.all())

        self.assertEqual(
            set(filterset.qs.values_list("pk", flat=True)),
            {self.second_individual.pk},
        )
