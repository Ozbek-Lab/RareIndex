from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory, TestCase
from django.utils import timezone

from lab.filters import IndividualFilter, VariantFilter
from lab.models import (
    Analysis,
    AnalysisType,
    Individual,
    Note,
    Pipeline,
    PipelineType,
    Sample,
    SampleType,
    Test,
    TestType,
)
from variant.models import SNV, Variant


class NoteSearchFilterTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="note-search-filter-user")
        self.other_user = User.objects.create_user(username="note-search-other-user")

        self.first_individual = Individual.objects.create(
            full_name="First",
            created_by=self.user,
        )
        self.second_individual = Individual.objects.create(
            full_name="Second",
            created_by=self.user,
        )

        sample_type = SampleType.objects.create(name="Blood", created_by=self.user)
        self.first_sample = Sample.objects.create(
            individual=self.first_individual,
            sample_type=sample_type,
            created_by=self.user,
        )
        test_type = TestType.objects.create(name="Genome", created_by=self.user)
        self.first_test = Test.objects.create(
            sample=self.first_sample,
            test_type=test_type,
            created_by=self.user,
        )
        pipeline_type = PipelineType.objects.create(
            name="Short Reads",
            created_by=self.user,
        )
        self.first_pipeline = Pipeline.objects.create(
            test=self.first_test,
            type=pipeline_type,
            performed_by=self.user,
            performed_date=timezone.now().date(),
            created_by=self.user,
        )
        analysis_type = AnalysisType.objects.create(
            name="Diagnostic",
            created_by=self.user,
        )
        self.first_analysis = Analysis.objects.create(
            pipeline=self.first_pipeline,
            type=analysis_type,
            created_by=self.user,
        )

        self.first_variant = Variant.objects.create(
            assembly_version="hg38",
            chromosome="chr1",
            start=100,
            end=100,
            individual=self.first_individual,
            created_by=self.user,
            zygosity="het",
        )
        self.first_other_variant = Variant.objects.create(
            assembly_version="hg38",
            chromosome="chr2",
            start=200,
            end=200,
            individual=self.first_individual,
            created_by=self.user,
            zygosity="hom",
        )
        self.second_variant = Variant.objects.create(
            assembly_version="hg38",
            chromosome="chr3",
            start=300,
            end=300,
            individual=self.second_individual,
            created_by=self.user,
            zygosity="het",
        )

    def _request_for(self, user):
        request = self.factory.get("/")
        request.user = user
        return request

    def _add_note(self, obj, content, user=None, private_owner=None):
        return Note.objects.create(
            content=content,
            user=user or self.user,
            private_owner=private_owner,
            content_type=ContentType.objects.get_for_model(obj.__class__),
            object_id=obj.pk,
        )

    def assert_individual_ids(self, data, expected_ids, user=None):
        filterset = IndividualFilter(
            data=data,
            queryset=Individual.objects.all(),
            request=self._request_for(user or self.user),
        )
        self.assertTrue(filterset.form.is_valid(), filterset.form.errors)
        self.assertEqual(set(filterset.qs.values_list("pk", flat=True)), expected_ids)

    def assert_variant_ids(self, data, expected_ids, user=None):
        filterset = VariantFilter(
            data=data,
            queryset=Variant.objects.all(),
            request=self._request_for(user or self.user),
        )
        self.assertTrue(filterset.form.is_valid(), filterset.form.errors)
        self.assertEqual(set(filterset.qs.values_list("pk", flat=True)), expected_ids)

    def test_individual_note_search_requires_toggle(self):
        self._add_note(self.first_analysis, "contains extraction-review-marker")

        data = {"search": "extraction-review-marker"}
        self.assert_individual_ids(data, set())

        data["search_notes"] = "1"
        self.assert_individual_ids(data, {self.first_individual.pk})

    def test_individual_note_search_includes_variant_notes(self):
        self._add_note(self.second_variant, "contains candidate-note-marker")

        self.assert_individual_ids(
            {"search": "candidate-note-marker", "search_notes": "1"},
            {self.second_individual.pk},
        )

    def test_variant_note_search_keeps_direct_variant_notes_scoped(self):
        self._add_note(self.first_variant, "contains variant-only-marker")

        self.assert_variant_ids(
            {"search": "variant-only-marker", "search_notes": "1"},
            {self.first_variant.pk},
        )

    def test_variant_note_search_includes_related_workflow_notes(self):
        self._add_note(self.first_sample, "contains sample-workflow-marker")

        self.assert_variant_ids(
            {"search": "sample-workflow-marker", "search_notes": "1"},
            {self.first_variant.pk, self.first_other_variant.pk},
        )

    def test_variant_note_search_includes_subtype_note_content_types(self):
        Note.objects.create(
            content="contains subtype-note-marker",
            user=self.user,
            content_type=ContentType.objects.get_for_model(SNV),
            object_id=self.first_variant.pk,
        )

        self.assert_variant_ids(
            {"search": "subtype-note-marker", "search_notes": "1"},
            {self.first_variant.pk},
        )

    def test_note_search_respects_private_notes(self):
        self._add_note(
            self.second_individual,
            "contains private-note-marker",
            user=self.other_user,
            private_owner=self.other_user,
        )

        data = {"search": "private-note-marker", "search_notes": "1"}
        self.assert_individual_ids(data, set(), user=self.user)
        self.assert_individual_ids(data, {self.second_individual.pk}, user=self.other_user)
