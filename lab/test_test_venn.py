import json
from io import StringIO
from math import cos, sin

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from lab.models import (
    Individual, PlotTemplate, Project, ProjectMembership, Sample, SampleType,
    Test as LabTest, TestType,
)
from lab.jwt_utils import issue_plot_token
from lab.notebooks._test_overlap import (
    INDIVIDUAL_VALUES, default_test_types, ellipse_layout,
    individual_test_memberships, overlap_counts, overlap_figure, overlap_table,
    test_type_options,
)


class TestOverlapCountingTests(SimpleTestCase):
    def test_duplicates_and_unselected_tests_do_not_change_exact_regions(self):
        memberships = individual_test_memberships([
            {"id": 1, "samples__tests__test_type_id": 10},
            {"id": 1, "samples__tests__test_type_id": 10},
            {"id": 1, "samples__tests__test_type_id": 20},
            {"id": 2, "samples__tests__test_type_id": 10},
            {"id": 3, "samples__tests__test_type_id": 20},
            {"id": 4, "samples__tests__test_type_id": 30},
            {"id": 5, "samples__tests__test_type_id": None},
        ])
        self.assertEqual(overlap_counts(memberships, [10, 20]), {0: 2, 1: 1, 2: 1, 3: 1})
        self.assertEqual(overlap_counts(memberships, [10]), {0: 3, 1: 2})
        self.assertEqual(overlap_counts(memberships, []), {0: 5})

    def test_every_combination_is_counted_once_for_small_and_large_selections(self):
        for size in (3, 4, 5, 8):
            with self.subTest(size=size):
                memberships = {
                    mask: {index for index in range(size) if mask & (1 << index)}
                    for mask in range(1 << size)
                }
                counts = overlap_counts(memberships, list(range(size)))
                self.assertEqual(counts, dict.fromkeys(range(1 << size), 1))
                self.assertEqual(sum(row["Individuals"] for row in overlap_table(counts, list(map(str, range(size))))), len(memberships))

    def test_empty_cohort_retains_zero_regions(self):
        self.assertEqual(overlap_counts({}, [1, 2]), {0: 0, 1: 0, 2: 0, 3: 0})
        self.assertEqual(overlap_counts({}, list(range(8))), {0: 0})

    def test_catalog_options_preserve_duplicate_names_and_default_to_sequencing(self):
        catalog = [
            {"id": 1, "name": "Sanger"}, {"id": 2, "name": "WES"},
            {"id": 3, "name": "WGS"}, {"id": 4, "name": "RNA Seq"},
            {"id": 5, "name": "WES"},
        ]
        self.assertEqual(len(test_type_options(catalog)), 5)
        self.assertEqual(default_test_types(catalog), [2, 3, 4])
        catalog.insert(0, {"id": 6, "name": "RNA-seq"})
        self.assertEqual(default_test_types(catalog), [2, 3, 6])
        self.assertEqual(default_test_types([]), [])

    def test_ellipse_labels_lie_inside_the_correct_exact_regions(self):
        for number in (4, 5):
            ellipses, positions = ellipse_layout(number)
            self.assertEqual(set(positions), set(range(1, 1 << number)))
            for expected_mask, (x, y) in positions.items():
                actual_mask = 0
                for i, (cx, cy, a, b, angle) in enumerate(ellipses):
                    u = (x - cx) * cos(angle) + (y - cy) * sin(angle)
                    v = -(x - cx) * sin(angle) + (y - cy) * cos(angle)
                    if (u / a) ** 2 + (v / b) ** 2 < 1:
                        actual_mask |= 1 << i
                self.assertEqual(actual_mask, expected_mask)

    def test_figures_keep_zero_and_outside_counts_and_do_not_use_bars(self):
        for number in range(9):
            with self.subTest(number=number):
                counts = overlap_counts({1: set()}, list(range(number)))
                figure = overlap_figure(counts, [f"Test {i}" for i in range(number)])
                self.assertTrue(all(trace.type == "scatter" for trace in figure.data))
                self.assertTrue(any("<b>1</b>" in annotation.text for annotation in figure.layout.annotations))
                if number in (4, 5):
                    self.assertEqual(len(figure.data[-1].text), (1 << number) - 1)
                if number > 5:
                    self.assertEqual(len(figure.data), number)
                    self.assertTrue(all(trace.mode == "lines" for trace in figure.data))


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class TestVennIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(username="venn-owner", is_staff=True)
        cls.member = User.objects.create_user(username="venn-viewer")
        cls.wes = TestType.objects.create(name="WES", created_by=cls.staff)
        cls.wgs = TestType.objects.create(name="WGS", created_by=cls.staff)
        cls.rna = TestType.objects.create(name="RNA seq", created_by=cls.staff)
        cls.unused = TestType.objects.create(name="Unused type", created_by=cls.staff)
        cls.sample_type = SampleType.objects.create(name="Blood", created_by=cls.staff)
        cls.individuals = [Individual.objects.create(created_by=cls.staff) for _ in range(6)]
        cls.project = Project.objects.create(name="Venn cohort", created_by=cls.staff)
        cls.project.individuals.add(*cls.individuals[:5])
        ProjectMembership.objects.create(
            project=cls.project, user=cls.member, role=ProjectMembership.Role.VIEWER,
            created_by=cls.staff,
        )
        # Both tests across samples, duplicates, WES only, RNA only, no tests,
        # no samples, and an inaccessible WGS individual.
        for individual_index, test_types in [(0, [cls.wes, cls.wes]), (0, [cls.wgs]),
                                              (1, [cls.wes]), (2, [cls.rna]),
                                              (3, []), (5, [cls.wgs])]:
            sample = Sample.objects.create(
                individual=cls.individuals[individual_index], sample_type=cls.sample_type,
                created_by=cls.staff,
            )
            for test_type in test_types:
                LabTest.objects.create(sample=sample, test_type=test_type, created_by=cls.staff)
        LabTest.objects.create(test_type=cls.wgs, created_by=cls.staff)  # Unattached test.

    def fetch_rows(self, model="Individual", values=INDIVIDUAL_VALUES, filters=None):
        params = {"model": model, "config": json.dumps({"values": values})}
        if filters:
            params["visualization_filters"] = json.dumps(filters)
        response = self.client.get(reverse("lab:generic_plot_data"), params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["data"]

    def test_api_preserves_untested_people_deduplicates_and_enforces_project_scope(self):
        self.client.force_login(self.member)
        memberships = individual_test_memberships(self.fetch_rows())
        self.assertEqual(set(memberships), {person.pk for person in self.individuals[:5]})
        self.assertEqual(overlap_counts(memberships, [self.wes.pk, self.wgs.pk]), {0: 3, 1: 1, 2: 0, 3: 1})

    def test_cohort_test_filter_does_not_remove_other_test_memberships(self):
        self.client.force_login(self.member)
        memberships = individual_test_memberships(self.fetch_rows(filters={"samples__tests__test_type": [self.wes.name]}))
        self.assertEqual(overlap_counts(memberships, [self.wes.pk, self.wgs.pk]), {0: 0, 1: 1, 2: 0, 3: 1})

    def test_catalog_includes_unused_types_even_with_cohort_filters(self):
        self.client.force_login(self.member)
        rows = self.fetch_rows("TestType", ["id", "name"], {"samples__tests__test_type": [self.wes.name]})
        self.assertEqual({row["id"] for row in rows}, {self.wes.pk, self.wgs.pk, self.rna.pk, self.unused.pk})

    def test_notebook_bearer_token_preserves_project_scope_and_cohort_filters(self):
        token = issue_plot_token(self.member, {
            "samples__tests__test_type": [self.wes.name],
        })
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        memberships = individual_test_memberships(self.fetch_rows())
        self.assertEqual(overlap_counts(memberships, [self.wes.pk, self.wgs.pk]), {0: 0, 1: 1, 2: 0, 3: 1})

    def test_catalog_requires_authentication(self):
        response = self.client.get(reverse("lab:generic_plot_data"), {"model": "TestType"})
        self.assertEqual(response.status_code, 401)

    def test_catalog_cannot_be_used_to_read_individuals_through_reverse_joins(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("lab:generic_plot_data"), {
            "model": "TestType",
            "config": json.dumps({"values": ["test__sample__individual__id"]}),
        })
        self.assertEqual(response.status_code, 400)

    def test_seeded_notebook_is_published_and_appears_in_dynamic_visualizations(self):
        call_command("seed_plot_templates", stdout=StringIO())
        call_command("seed_plot_templates", stdout=StringIO())
        template = PlotTemplate.objects.get(slug="individual-test-venn")
        self.assertTrue(template.is_published)
        template.full_clean()
        self.staff.is_superuser = True
        self.staff.save(update_fields=["is_superuser"])
        self.client.force_login(self.staff)
        response = self.client.get(reverse("lab:map_visualization"))
        self.assertContains(response, "Individual Test Venn Diagram")
        self.assertContains(response, "file=test_venn.py")
        self.assertContains(response, 'title="Individual Test Venn Diagram"', count=1)

    def test_visualizations_includes_venn_without_database_registration(self):
        self.staff.is_superuser = True
        self.staff.save(update_fields=["is_superuser"])
        self.client.force_login(self.staff)
        response = self.client.get(reverse("lab:map_visualization"))
        self.assertContains(response, r"currentTab = 'individual\u002Dtest\u002Dvenn'")
        self.assertContains(response, "file=test_venn.py")
        self.assertContains(response, 'title="Individual Test Venn Diagram"', count=1)
        self.assertFalse(PlotTemplate.objects.filter(slug="individual-test-venn").exists())
