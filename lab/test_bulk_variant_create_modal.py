from datetime import date

from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.test import TestCase
from django.test import override_settings
from django.template.loader import render_to_string
from django.urls import reverse

from lab.models import (
    Analysis,
    AnalysisType,
    CrossIdentifier,
    IdentifierType,
    Individual,
    Pipeline,
    PipelineType,
    Sample,
    SampleType,
    Test as LabTest,
    TestType,
)
from variant.models import CNV, Repeat, SNV, SV, Variant
from variant.signals import annotate_and_link_genes


@override_settings(
    SECURE_SSL_REDIRECT=False,
    MIDDLEWARE=[
        middleware
        for middleware in settings.MIDDLEWARE
        if middleware != "reversion.middleware.RevisionMiddleware"
    ],
)
class BulkVariantCreateModalTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for model in (SNV, CNV, SV, Repeat):
            post_save.disconnect(annotate_and_link_genes, sender=model)

    @classmethod
    def tearDownClass(cls):
        for model in (SNV, CNV, SV, Repeat):
            post_save.connect(annotate_and_link_genes, sender=model)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(
            username="bulk-variant-user",
            password="password",
        )
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Variant),
                codename="add_variant",
            )
        )
        self.client.force_login(self.user)

        self.id_type = IdentifierType.objects.create(
            name="RareBoost",
            use_priority=1,
            created_by=self.user,
        )
        self.blood_type = SampleType.objects.create(name="Blood", created_by=self.user)
        self.saliva_type = SampleType.objects.create(name="Saliva", created_by=self.user)
        self.wgs_type = TestType.objects.create(name="WGS", created_by=self.user)
        self.wes_type = TestType.objects.create(name="WES", created_by=self.user)
        self.pipeline_type = PipelineType.objects.create(
            name="GATK",
            version="4.0",
            created_by=self.user,
        )
        self.other_pipeline_type = PipelineType.objects.create(
            name="Dragen",
            version="1.2",
            created_by=self.user,
        )
        self.analysis_type = AnalysisType.objects.create(
            name="Initial Analysis",
            created_by=self.user,
        )
        self.reanalysis_type = AnalysisType.objects.create(
            name="Reanalysis",
            created_by=self.user,
        )

        self.first = Individual.objects.create(full_name="First Individual", created_by=self.user)
        self.second = Individual.objects.create(full_name="Second Individual", created_by=self.user)
        self.no_analysis = Individual.objects.create(
            full_name="No Analysis Individual",
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.first,
            id_type=self.id_type,
            id_value="RB_2026_401.1",
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.second,
            id_type=self.id_type,
            id_value="RB_2026_402.1",
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.no_analysis,
            id_type=self.id_type,
            id_value="RB_2026_403.1",
            created_by=self.user,
        )

        self.first_sample = Sample.objects.create(
            individual=self.first,
            sample_type=self.blood_type,
            receipt_date=date(2026, 1, 15),
            created_by=self.user,
        )
        self.first_second_sample = Sample.objects.create(
            individual=self.first,
            sample_type=self.saliva_type,
            created_by=self.user,
        )
        self.second_sample = Sample.objects.create(
            individual=self.second,
            sample_type=self.saliva_type,
            created_by=self.user,
        )
        self.no_analysis_sample = Sample.objects.create(
            individual=self.no_analysis,
            sample_type=self.blood_type,
            created_by=self.user,
        )
        self.first_test = LabTest.objects.create(
            sample=self.first_sample,
            test_type=self.wgs_type,
            created_by=self.user,
        )
        self.first_second_test = LabTest.objects.create(
            sample=self.first_second_sample,
            test_type=self.wes_type,
            created_by=self.user,
        )
        self.second_test = LabTest.objects.create(
            sample=self.second_sample,
            test_type=self.wgs_type,
            created_by=self.user,
        )
        self.no_analysis_test = LabTest.objects.create(
            sample=self.no_analysis_sample,
            test_type=self.wgs_type,
            created_by=self.user,
        )
        self.first_pipeline = Pipeline.objects.create(
            test=self.first_test,
            type=self.pipeline_type,
            performed_date=date(2026, 8, 20),
            performed_by=self.user,
            created_by=self.user,
        )
        self.first_second_pipeline = Pipeline.objects.create(
            test=self.first_second_test,
            type=self.other_pipeline_type,
            performed_date=date(2026, 8, 21),
            performed_by=self.user,
            created_by=self.user,
        )
        self.second_pipeline = Pipeline.objects.create(
            test=self.second_test,
            type=self.pipeline_type,
            performed_date=date(2026, 8, 22),
            performed_by=self.user,
            created_by=self.user,
        )
        self.no_analysis_pipeline = Pipeline.objects.create(
            test=self.no_analysis_test,
            type=self.pipeline_type,
            performed_date=date(2026, 8, 23),
            performed_by=self.user,
            created_by=self.user,
        )
        self.first_analysis = Analysis.objects.create(
            pipeline=self.first_pipeline,
            type=self.analysis_type,
            performed_date=date(2026, 8, 24),
            created_by=self.user,
        )
        self.first_second_analysis = Analysis.objects.create(
            pipeline=self.first_second_pipeline,
            type=self.reanalysis_type,
            performed_date=date(2026, 8, 25),
            created_by=self.user,
        )
        self.second_analysis = Analysis.objects.create(
            pipeline=self.second_pipeline,
            type=self.analysis_type,
            performed_date=date(2026, 8, 26),
            created_by=self.user,
        )

    def test_bulk_create_dropdown_renders_variant_modal_url(self):
        html = render_to_string("lab/components/bulk_create_dropdown.html")

        self.assertIn(reverse("lab:bulk_variant_create_modal"), html)
        self.assertIn('data-bulk-create-type="variant"', html)
        self.assertIn("Variants", html)

    def test_bulk_variant_create_modal_returns_matching_individual_ids(self):
        response = self.client.post(
            reverse("lab:bulk_variant_create_modal"),
            {"ids": "RB_2026_401.1, missing-id\nRB_2026_402.1"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bulk Create Variants")
        self.assertContains(response, "Add Variants")
        self.assertContains(response, str(self.first.pk))
        self.assertContains(response, "RB_2026_401.1")
        self.assertContains(response, str(self.second.pk))
        self.assertContains(response, "RB_2026_402.1")
        self.assertNotContains(response, "Object ID")

    def test_add_variants_button_renders_bulk_variant_rows_with_toggle(self):
        response = self.client.post(
            reverse("lab:bulk_variant_create_form"),
            {"individual_ids": [str(self.first.pk), str(self.second.pk)]},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Variants")
        self.assertContains(response, "Analysis")
        self.assertContains(response, "Analysis Object")
        self.assertContains(response, "Variant Details")
        self.assertContains(response, "bulk-variant-details")
        self.assertContains(response, "grid-template-columns: repeat(16")
        self.assertContains(response, "min-width: 72rem")
        self.assertContains(response, "Zygosity")
        self.assertContains(response, "variants-0-use_analysis")
        self.assertContains(response, "toggle toggle-primary toggle-xs")
        self.assertContains(response, 'x-model="linked"')
        self.assertContains(response, "variants-0-sample")
        self.assertContains(response, "variants-0-test")
        self.assertContains(response, "variants-0-pipeline")
        self.assertContains(response, "variants-0-analysis")
        self.assertContains(response, "variants-0-variant_kind")
        self.assertContains(response, "variants-0-chromosome")
        self.assertContains(response, "variants-0-start")
        self.assertContains(response, "variants-0-reference")
        self.assertContains(response, "variants-0-alternate")
        self.assertNotContains(response, "Object ID")

    def test_bulk_variant_rows_only_show_samples_from_each_individual(self):
        response = self.client.post(
            reverse("lab:bulk_variant_create_form"),
            {"individual_ids": [str(self.first.pk), str(self.second.pk)]},
            HTTP_HX_REQUEST="true",
        )

        html = response.content.decode()
        first_select = html.split('id="id_variants-0-sample"', 1)[1].split(
            "</select>", 1
        )[0]
        second_select = html.split('id="id_variants-1-sample"', 1)[1].split(
            "</select>", 1
        )[0]

        self.assertIn(f"value=\"{self.first_sample.pk}\"", first_select)
        self.assertIn(f"value=\"{self.first_second_sample.pk}\"", first_select)
        self.assertNotIn(f"value=\"{self.second_sample.pk}\"", first_select)
        self.assertIn(f"value=\"{self.second_sample.pk}\"", second_select)
        self.assertNotIn(f"value=\"{self.first_sample.pk}\"", second_select)

    def test_variant_test_options_update_from_selected_sample_and_reset_children(self):
        response = self.client.get(
            reverse("lab:bulk_variant_test_options"),
            {
                "variants-0-sample": str(self.first_second_sample.pk),
                "field_name": "variants-0-test",
                "field_id": "id_variants-0-test",
                "pipeline_field_name": "variants-0-pipeline",
                "pipeline_field_id": "id_variants-0-pipeline",
                "pipeline_cell_id": "pipeline-options-variants-0",
                "analysis_field_name": "variants-0-analysis",
                "analysis_field_id": "id_variants-0-analysis",
                "analysis_cell_id": "analysis-options-variants-0",
                "individual_id": str(self.first.pk),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="variants-0-test"')
        self.assertContains(response, f"value=\"{self.first_second_test.pk}\"")
        self.assertContains(response, "WES")
        self.assertContains(response, 'id="pipeline-options-variants-0"')
        self.assertContains(response, 'id="analysis-options-variants-0"')
        self.assertContains(response, 'hx-swap-oob="innerHTML"')
        self.assertNotContains(response, f"value=\"{self.first_test.pk}\"")
        self.assertNotContains(response, f"value=\"{self.second_test.pk}\"")

    def test_variant_pipeline_options_update_from_selected_test_and_reset_analysis(self):
        response = self.client.get(
            reverse("lab:bulk_variant_pipeline_options"),
            {
                "variants-0-test": str(self.first_test.pk),
                "field_name": "variants-0-pipeline",
                "field_id": "id_variants-0-pipeline",
                "analysis_field_name": "variants-0-analysis",
                "analysis_field_id": "id_variants-0-analysis",
                "analysis_cell_id": "analysis-options-variants-0",
                "sample_id": str(self.first_sample.pk),
                "individual_id": str(self.first.pk),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="variants-0-pipeline"')
        self.assertContains(response, f"value=\"{self.first_pipeline.pk}\"")
        self.assertContains(response, "GATK")
        self.assertContains(response, 'id="analysis-options-variants-0"')
        self.assertContains(response, 'hx-swap-oob="innerHTML"')
        self.assertNotContains(response, f"value=\"{self.first_second_pipeline.pk}\"")
        self.assertNotContains(response, f"value=\"{self.second_pipeline.pk}\"")

    def test_variant_analysis_options_update_from_selected_pipeline(self):
        response = self.client.get(
            reverse("lab:bulk_variant_analysis_options"),
            {
                "variants-0-pipeline": str(self.first_pipeline.pk),
                "field_name": "variants-0-analysis",
                "field_id": "id_variants-0-analysis",
                "test_id": str(self.first_test.pk),
                "sample_id": str(self.first_sample.pk),
                "individual_id": str(self.first.pk),
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="variants-0-analysis"')
        self.assertContains(response, f"value=\"{self.first_analysis.pk}\"")
        self.assertContains(response, "Initial Analysis")
        self.assertNotContains(response, f"value=\"{self.first_second_analysis.pk}\"")
        self.assertNotContains(response, f"value=\"{self.second_analysis.pk}\"")

    def test_bulk_variant_rows_warn_but_still_allow_direct_variants(self):
        response = self.client.post(
            reverse("lab:bulk_variant_create_form"),
            {"individual_ids": [str(self.no_analysis.pk)]},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This individual's pipelines have no analyses.")
        self.assertContains(response, "Create Variants")

    def test_bulk_variant_rows_create_direct_individual_variant_when_toggle_is_off(self):
        response = self.client.post(
            reverse("lab:bulk_variant_create_form"),
            {
                "bulk_variant_action": "create",
                "variants-TOTAL_FORMS": "1",
                "variants-INITIAL_FORMS": "0",
                "variants-MIN_NUM_FORMS": "1",
                "variants-MAX_NUM_FORMS": "1000",
                "variants-0-individual": str(self.no_analysis.pk),
                "variants-0-variant_kind": "snv",
                "variants-0-chromosome": "chr10",
                "variants-0-start": "77984023",
                "variants-0-reference": "A",
                "variants-0-alternate": "G",
                "variants-0-assembly_version": "hg38",
                "variants-0-zygosity": "het",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1 variant created")

        variant = SNV.objects.get()
        self.assertEqual(variant.individual, self.no_analysis)
        self.assertIsNone(variant.analysis)
        self.assertEqual(variant.chromosome, "chr10")
        self.assertEqual(variant.start, 77984023)
        self.assertEqual(variant.end, 77984023)
        self.assertEqual(variant.reference, "A")
        self.assertEqual(variant.alternate, "G")
        self.assertEqual(variant.zygosity, "het")
        self.assertEqual(variant.created_by, self.user)

    def test_bulk_variant_rows_create_analysis_linked_variant_when_toggle_is_on(self):
        response = self.client.post(
            reverse("lab:bulk_variant_create_form"),
            {
                "bulk_variant_action": "create",
                "variants-TOTAL_FORMS": "1",
                "variants-INITIAL_FORMS": "0",
                "variants-MIN_NUM_FORMS": "1",
                "variants-MAX_NUM_FORMS": "1000",
                "variants-0-individual": str(self.first.pk),
                "variants-0-use_analysis": "on",
                "variants-0-sample": str(self.first_sample.pk),
                "variants-0-test": str(self.first_test.pk),
                "variants-0-pipeline": str(self.first_pipeline.pk),
                "variants-0-analysis": str(self.first_analysis.pk),
                "variants-0-variant_kind": "sv",
                "variants-0-chromosome": "chr20",
                "variants-0-start": "35679278",
                "variants-0-end": "35685149",
                "variants-0-sv_type": "deletion",
                "variants-0-assembly_version": "hg38",
                "variants-0-zygosity": "hom",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1 variant created")

        variant = SV.objects.get()
        self.assertEqual(variant.individual, self.first)
        self.assertEqual(variant.analysis, self.first_analysis)
        self.assertEqual(variant.chromosome, "chr20")
        self.assertEqual(variant.start, 35679278)
        self.assertEqual(variant.end, 35685149)
        self.assertEqual(variant.sv_type, "deletion")
        self.assertEqual(variant.zygosity, "hom")

    def test_bulk_variant_rows_create_cnv_and_repeat_records(self):
        response = self.client.post(
            reverse("lab:bulk_variant_create_form"),
            {
                "bulk_variant_action": "create",
                "variants-TOTAL_FORMS": "2",
                "variants-INITIAL_FORMS": "0",
                "variants-MIN_NUM_FORMS": "1",
                "variants-MAX_NUM_FORMS": "1000",
                "variants-0-individual": str(self.first.pk),
                "variants-0-variant_kind": "cnv",
                "variants-0-chromosome": "chr7",
                "variants-0-start": "100318423",
                "variants-0-end": "100321323",
                "variants-0-cnv_type": "gain",
                "variants-0-assembly_version": "hg38",
                "variants-0-zygosity": "het",
                "variants-1-individual": str(self.second.pk),
                "variants-1-variant_kind": "repeat",
                "variants-1-chromosome": "chr7",
                "variants-1-start": "117199644",
                "variants-1-repeat_unit": "CAG",
                "variants-1-repeat_count": "45",
                "variants-1-assembly_version": "hg38",
                "variants-1-zygosity": "unknown",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 variants created")
        self.assertEqual(CNV.objects.count(), 1)
        self.assertEqual(Repeat.objects.count(), 1)
        self.assertEqual(CNV.objects.get().cnv_type, "gain")
        self.assertEqual(Repeat.objects.get().repeat_unit, "CAG")
        self.assertEqual(Repeat.objects.get().repeat_count, 45)

    def test_bulk_variant_rows_require_analysis_when_toggle_is_on(self):
        response = self.client.post(
            reverse("lab:bulk_variant_create_form"),
            {
                "bulk_variant_action": "create",
                "variants-TOTAL_FORMS": "1",
                "variants-INITIAL_FORMS": "0",
                "variants-MIN_NUM_FORMS": "1",
                "variants-MAX_NUM_FORMS": "1000",
                "variants-0-individual": str(self.first.pk),
                "variants-0-use_analysis": "on",
                "variants-0-sample": str(self.first_sample.pk),
                "variants-0-test": str(self.first_test.pk),
                "variants-0-pipeline": str(self.first_pipeline.pk),
                "variants-0-analysis": "",
                "variants-0-variant_kind": "snv",
                "variants-0-chromosome": "chr10",
                "variants-0-start": "77984023",
                "variants-0-reference": "A",
                "variants-0-alternate": "G",
                "variants-0-assembly_version": "hg38",
                "variants-0-zygosity": "het",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose an analysis.")
        self.assertEqual(Variant.objects.count(), 0)

    def test_bulk_variant_rows_reject_analysis_from_different_pipeline(self):
        response = self.client.post(
            reverse("lab:bulk_variant_create_form"),
            {
                "bulk_variant_action": "create",
                "variants-TOTAL_FORMS": "1",
                "variants-INITIAL_FORMS": "0",
                "variants-MIN_NUM_FORMS": "1",
                "variants-MAX_NUM_FORMS": "1000",
                "variants-0-individual": str(self.first.pk),
                "variants-0-use_analysis": "on",
                "variants-0-sample": str(self.first_sample.pk),
                "variants-0-test": str(self.first_test.pk),
                "variants-0-pipeline": str(self.first_pipeline.pk),
                "variants-0-analysis": str(self.first_second_analysis.pk),
                "variants-0-variant_kind": "snv",
                "variants-0-chromosome": "chr10",
                "variants-0-start": "77984023",
                "variants-0-reference": "A",
                "variants-0-alternate": "G",
                "variants-0-assembly_version": "hg38",
                "variants-0-zygosity": "het",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertEqual(Variant.objects.count(), 0)

    def test_bulk_variant_rows_reject_invalid_variant_fields(self):
        response = self.client.post(
            reverse("lab:bulk_variant_create_form"),
            {
                "bulk_variant_action": "create",
                "variants-TOTAL_FORMS": "1",
                "variants-INITIAL_FORMS": "0",
                "variants-MIN_NUM_FORMS": "1",
                "variants-MAX_NUM_FORMS": "1000",
                "variants-0-individual": str(self.first.pk),
                "variants-0-variant_kind": "snv",
                "variants-0-chromosome": "chr10",
                "variants-0-start": "77984023",
                "variants-0-reference": "N",
                "variants-0-alternate": "G",
                "variants-0-assembly_version": "hg38",
                "variants-0-zygosity": "het",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Use A, C, G, and T only.")
        self.assertEqual(Variant.objects.count(), 0)

    def test_bulk_variant_endpoints_require_add_variant_permission(self):
        self.user.user_permissions.clear()

        endpoints = [
            ("get", reverse("lab:bulk_variant_create_modal")),
            ("post", reverse("lab:bulk_variant_create_form")),
            ("get", reverse("lab:bulk_variant_test_options")),
            ("get", reverse("lab:bulk_variant_pipeline_options")),
            ("get", reverse("lab:bulk_variant_analysis_options")),
        ]
        for method, url in endpoints:
            response = getattr(self.client, method)(url)
            self.assertEqual(response.status_code, 403)
