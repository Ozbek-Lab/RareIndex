from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.test import SimpleTestCase, TestCase

from lab.filters import IndividualFilter, VariantFilter
from lab.models import Individual
from variant.forms import DelinsForm, RepeatForm, SNVForm, VariantTypeForm
from variant.models import CNV, SNV, SV, Repeat, Variant, delins, normalize_chromosome
from variant.signals import annotate_and_link_genes


class VariantFormTypeTests(SimpleTestCase):
    def test_variant_type_form_includes_delins(self):
        choices = list(VariantTypeForm().fields["variant_type"].choices)

        self.assertIn(("delins", "Delins"), choices)

    def test_snv_form_requires_single_base_alleles(self):
        form = SNVForm(
            data={
                "assembly_version": "hg38",
                "snv_string": "chr3:33114394TGC>T",
                "zygosity": "het",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("SNV requires single-base", form.errors["snv_string"][0])

    def test_delins_form_accepts_multi_base_change(self):
        form = DelinsForm(
            data={
                "assembly_version": "hg38",
                "delins_string": "chr3:33114394TGC>T",
                "zygosity": "het",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        variant = form.save(commit=False)
        self.assertEqual(variant.chromosome, "chr3")
        self.assertEqual(variant.reference, "TGC")
        self.assertEqual(variant.alternate, "T")

    def test_delins_form_rejects_single_base_change(self):
        form = DelinsForm(
            data={
                "assembly_version": "hg38",
                "delins_string": "chr10:77984023A>G",
                "zygosity": "het",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Use SNV", form.errors["delins_string"][0])

    def test_repeat_form_normalizes_and_validates_repeat_fields(self):
        form = RepeatForm(
            data={
                "assembly_version": "hg38",
                "chromosome": "chr4",
                "start": 100,
                "end": 110,
                "zygosity": "het",
                "repeat_unit": "cag",
                "repeat_count": 42,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["repeat_unit"], "CAG")

    def test_normalize_chromosome_handles_case_and_mitochondrial_alias(self):
        self.assertEqual(normalize_chromosome("CHR1"), "chr1")
        self.assertEqual(normalize_chromosome("mt"), "chrM")


class VariantModelTypeTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for sender in (SNV, delins, CNV, SV, Repeat):
            post_save.disconnect(annotate_and_link_genes, sender=sender)

    @classmethod
    def tearDownClass(cls):
        for sender in (SNV, delins, CNV, SV, Repeat):
            post_save.connect(annotate_and_link_genes, sender=sender)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(username="variant-type-user")
        self.individual = Individual.objects.create(
            full_name="Variant Type Person",
            created_by=self.user,
        )

    def test_base_variant_resolves_delins_display(self):
        variant = delins.objects.create(
            assembly_version="hg38",
            chromosome="3",
            start=33114394,
            end=33114394,
            individual=self.individual,
            created_by=self.user,
            zygosity="het",
            reference="TGC",
            alternate="T",
        )

        base_variant = Variant.objects.select_related("delins").get(pk=variant.pk)

        self.assertEqual(base_variant.type, "delins")
        self.assertEqual(base_variant.type_label, "Delins")
        self.assertEqual(base_variant.change_display, "TGC>T")
        self.assertEqual(base_variant.display_name, "chr3:33114394 TGC>T")
        self.assertEqual(base_variant.sequence_variant_id, "chr3-33114394-TGC-T")

    def test_base_variant_resolves_structural_display(self):
        variant = CNV.objects.create(
            assembly_version="hg38",
            chromosome="chr7",
            start=100318423,
            end=100321323,
            individual=self.individual,
            created_by=self.user,
            zygosity="het",
            cnv_type="gain",
            copy_number=4,
        )

        base_variant = Variant.objects.select_related("cnv").get(pk=variant.pk)

        self.assertEqual(base_variant.type, "CNV")
        self.assertEqual(base_variant.change_display, "Gain (copy number 4)")
        self.assertEqual(
            base_variant.display_name,
            "chr7:100318423-100321323 Gain (copy number 4)",
        )

    def test_variant_filter_matches_delins_type(self):
        variant = delins.objects.create(
            assembly_version="hg38",
            chromosome="chr3",
            start=33114394,
            end=33114394,
            individual=self.individual,
            created_by=self.user,
            zygosity="het",
            reference="TGC",
            alternate="T",
        )
        SNV.objects.create(
            assembly_version="hg38",
            chromosome="chr10",
            start=77984023,
            end=77984023,
            individual=self.individual,
            created_by=self.user,
            zygosity="het",
            reference="A",
            alternate="G",
        )

        filterset = VariantFilter(
            data={"variant_type": ["delins"]},
            queryset=Variant.objects.all(),
        )

        self.assertEqual(set(filterset.qs.values_list("pk", flat=True)), {variant.pk})

    def test_individual_filter_matches_delins_type(self):
        delins.objects.create(
            assembly_version="hg38",
            chromosome="chr3",
            start=33114394,
            end=33114394,
            individual=self.individual,
            created_by=self.user,
            zygosity="het",
            reference="TGC",
            alternate="T",
        )

        filterset = IndividualFilter(
            data={"variant_type": ["delins"]},
            queryset=Individual.objects.all(),
        )

        self.assertEqual(set(filterset.qs.values_list("pk", flat=True)), {self.individual.pk})
