from django.contrib.auth.models import User
from django.http import QueryDict
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from lab.filters import IndividualFilter, VariantFilter
from lab.models import Contact, Individual, Institution, Project, ProjectMembership
from variant.models import Variant


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class RelatedSelectionFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(username="picker-admin", password="password")
        cls.institutions = [
            Institution.objects.create(name=name, created_by=cls.user)
            for name in ["Institute A", "Institute A Annex"]
        ]
        cls.clinicians = [
            Contact.objects.create(full_name=name, created_by=cls.user)
            for name in ["Dr. Ayşe Öztürk", "Dr. O'Neil <Clinic>"]
        ]
        cls.people = [Individual.objects.create(created_by=cls.user) for _ in range(4)]
        cls.variants = [
            Variant.objects.create(individual=person, chromosome="1", start=i, end=i, created_by=cls.user)
            for i, person in enumerate(cls.people, 1)
        ]
        for relation, options in [("institution", cls.institutions), ("physicians", cls.clinicians)]:
            getattr(cls.people[0], relation).add(options[0])
            getattr(cls.people[1], relation).add(options[1])
            getattr(cls.people[2], relation).add(*options)

    def assert_matches(self, data, indexes):
        query = QueryDict(mutable=True)
        for name, values in data.items():
            query.setlist(name, values if isinstance(values, list) else [values])
        for filter_class, model, records in [
            (IndividualFilter, Individual, self.people), (VariantFilter, Variant, self.variants),
        ]:
            with self.subTest(filter_class=filter_class.__name__, data=data):
                filters = filter_class(data=query, queryset=model.objects.all())
                self.assertTrue(filters.is_valid(), filters.errors)
                self.assertCountEqual(filters.qs.values_list("pk", flat=True), [records[i].pk for i in indexes])

    def test_any_all_and_exclusions_on_both_pages(self):
        for name, options in [("institution", self.institutions), ("clinicians", self.clinicians)]:
            ids = [str(option.pk) for option in options]
            self.assert_matches({name: ids}, [0, 1, 2])
            self.assert_matches({name: ids, f"{name}__mode": "all"}, [2])
            self.assert_matches({name: [ids[0]]}, [0, 2])
            self.assert_matches({f"{name}__exclude": [ids[0]]}, [1, 3])
            self.assert_matches({name: ids, f"{name}__exclude": [ids[1]]}, [0])
            self.assert_matches({name: ["invalid"]}, [])
            self.assert_matches({name: ["999999"]}, [])
            self.assert_matches({f"{name}__exclude": ["invalid"]}, [0, 1, 2, 3])

    def test_group_combinations_keep_exclusions_global(self):
        selection = {"institution": [str(self.institutions[0].pk)], "clinicians": [str(self.clinicians[1].pk)]}
        self.assert_matches(selection, [2])
        self.assert_matches({**selection, "filter_group_mode": "any"}, [0, 1, 2])
        for name, option in [("institution", self.institutions[0]), ("clinicians", self.clinicians[0])]:
            self.assert_matches({**selection, "filter_group_mode": "any", f"{name}__exclude": [str(option.pk)]}, [1])
            self.assert_matches({"filter_group_mode": "any", f"{name}__exclude": [str(option.pk)]}, [1, 3])

    def test_options_follow_project_access(self):
        viewer = User.objects.create_user(username="picker-viewer")
        project = Project.objects.create(name="Visible", created_by=self.user)
        project.individuals.add(self.people[0])
        ProjectMembership.objects.create(project=project, user=viewer, role=ProjectMembership.Role.VIEWER, created_by=self.user)
        request = RequestFactory().get("/")
        request.user = viewer
        for filter_class, model in [(IndividualFilter, Individual), (VariantFilter, Variant)]:
            filters = filter_class(data={}, queryset=model.objects.all(), request=request)
            self.assertEqual(filters.institution_picker_options, [(self.institutions[0].pk, self.institutions[0].name)])
            self.assertEqual(filters.clinician_picker_options, [(self.clinicians[0].pk, self.clinicians[0].full_name)])

    def test_variant_options_only_include_people_with_variants(self):
        self.variants[1].delete()
        self.variants[2].delete()
        filters = VariantFilter(data={}, queryset=Variant.objects.all())
        self.assertEqual(filters.clinician_picker_options, [(self.clinicians[0].pk, self.clinicians[0].full_name)])

    def test_pages_and_htmx_filtering(self):
        self.client.force_login(self.user)
        for route, target, record in [
            ("individual_list", "individual-table-container", self.people[0]),
            ("variant_list", "variant-table-container", self.variants[0]),
        ]:
            data = {"clinicians": str(self.clinicians[0].pk), "institution__exclude": str(self.institutions[1].pk)}
            response = self.client.get(reverse(f"lab:{route}"), data)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'data-related-picker="institution"')
            self.assertContains(response, 'data-related-picker="clinicians"')
            self.assertContains(response, "Dr. Ayşe Öztürk")
            self.assertContains(response, "Dr. O&#x27;Neil &lt;Clinic&gt;")
            self.assertCountEqual(response.context["filter"].qs.values_list("pk", flat=True), [record.pk])
            response = self.client.get(reverse(f"lab:{route}"), data, HTTP_HX_REQUEST="true", HTTP_HX_TARGET=target)
            self.assertEqual(response.status_code, 200)
            self.assertCountEqual(response.context["filter"].qs.values_list("pk", flat=True), [record.pk])

    def test_picker_restores_selection_from_url(self):
        request = RequestFactory().get("/", {"clinicians": str(self.clinicians[0].pk), "clinicians__exclude": str(self.clinicians[1].pk)})
        html = render_to_string("lab/components/related_filter_picker.html", {
            "request": request, "name": "clinicians", "title": "Names", "placeholder": "Search clinicians...",
            "options": [(contact.pk, contact.full_name) for contact in self.clinicians],
        })
        self.assertIn(f"included: ['{self.clinicians[0].pk}',]", html)
        self.assertIn(f"excluded: ['{self.clinicians[1].pk}',]", html)
