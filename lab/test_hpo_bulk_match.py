import json

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from lab.views import hpo_bulk_match
from ontologies.models import Ontology, Term


class HPOBulkMatchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="bulk-hpo-user")
        ontology = Ontology.objects.create(type=1, label="HPO")
        cls.seizure = Term.objects.create(ontology=ontology, identifier="0001250", label="Seizure")
        cls.ataxia = Term.objects.create(ontology=ontology, identifier="0001251", label="Ataxia")

    def match(self, query):
        request = RequestFactory().get(reverse("lab:hpo_bulk_match"), {"q": query})
        request.user = self.user
        response = hpo_bulk_match(request)
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)["results"]

    def test_comma_and_newline_separators(self):
        for separator in [",", "\n", "\r\n", "\r", ",\n\n"]:
            with self.subTest(separator=repr(separator)):
                results = self.match(f"HP:0001250{separator}Ataxia")
                self.assertEqual([term["id"] for term in results], [self.seizure.pk, self.ataxia.pk])

    def test_mixed_separators_ignore_blanks_and_duplicates(self):
        results = self.match("\n Seizure,\r\n Ataxia \n HP:0001250, ,\n")
        self.assertEqual([term["id"] for term in results], [self.seizure.pk, self.ataxia.pk])

    def test_empty_or_unmatched_lines_are_ignored(self):
        self.assertEqual(self.match(" \n,\r\n "), [])
        results = self.match("NoSuchPhenotype\nHP:0001251")
        self.assertEqual([term["id"] for term in results], [self.ataxia.pk])


class PhenotypeBulkHPOTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from lab.models import Individual
        cls.editor = User.objects.create_superuser(username="phenotype-editor")
        cls.individual = Individual.objects.create(created_by=cls.editor)
        ontology = Ontology.objects.create(type=1, label="HPO")
        cls.seizure = Term.objects.create(ontology=ontology, identifier="0001250", label="Seizure")
        cls.ataxia = Term.objects.create(ontology=ontology, identifier="0001251", label="Ataxia")
        cls.individual.hpo_terms.add(cls.seizure)

    def post(self, query="", user=None, action="bulk_add", selected=None, term_id=None):
        from lab.htmx_views import manage_hpo_term
        data = {
            "action": action, "bulk_query": query,
            "hpo_terms": selected if selected is not None else [str(self.seizure.pk)],
        }
        if term_id is not None:
            data["term_id"] = str(term_id)
        request = RequestFactory().post(reverse("lab:hpo_manage", args=[self.individual.pk]), data)
        request.user = user or self.editor
        return manage_hpo_term(request, self.individual.pk)

    def open_editor(self):
        from lab.htmx_views import IndividualHPOEditView
        request = RequestFactory().get(reverse("lab:hpo_edit", args=[self.individual.pk]))
        request.user = self.editor
        return IndividualHPOEditView.as_view()(request, pk=self.individual.pk)

    def test_editor_contains_save_cancel_and_initial_selection(self):
        response = self.open_editor()
        self.assertContains(response, "Paste HPOs")
        self.assertContains(response, 'name="action" value="save"')
        self.assertContains(response, '>Save</button>')
        self.assertContains(response, '>Cancel</button>')
        self.assertContains(response, f'name="hpo_terms" value="{self.seizure.pk}"')
        self.assertContains(response, "commas or new lines")

    def test_bulk_add_only_changes_temporary_selection(self):
        response = self.post("HP:0001251\r\nSeizure, Ataxia")
        self.assertContains(response, f'name="hpo_terms" value="{self.ataxia.pk}"', count=1)
        self.assertContains(response, f'name="hpo_terms" value="{self.seizure.pk}"', count=1)
        self.assertEqual(list(self.individual.hpo_terms.values_list("pk", flat=True)), [self.seizure.pk])
        self.assertContains(response, "Matched 2 HPO term(s).")

    def test_single_add_and_remove_do_not_save(self):
        response = self.post(action="add", term_id=self.ataxia.pk)
        self.assertContains(response, f'name="hpo_terms" value="{self.ataxia.pk}"')
        response = self.post(action="remove", selected=[self.seizure.pk, self.ataxia.pk], term_id=self.seizure.pk)
        self.assertNotContains(response, f'name="hpo_terms" value="{self.seizure.pk}"')
        self.assertContains(response, f'name="hpo_terms" value="{self.ataxia.pk}"')
        self.assertEqual(list(self.individual.hpo_terms.values_list("pk", flat=True)), [self.seizure.pk])

    def test_save_applies_additions_and_removals(self):
        response = self.post(action="save", selected=[self.ataxia.pk])
        self.assertContains(response, "Ataxia")
        self.assertNotContains(response, "Seizure")
        self.assertEqual(list(self.individual.hpo_terms.values_list("pk", flat=True)), [self.ataxia.pk])
        self.assertNotContains(response, "Edit HPO Terms</h3>")

    def test_save_empty_selection_removes_all_terms(self):
        response = self.post(action="save", selected=[])
        self.assertContains(response, "No HPO terms recorded")
        self.assertFalse(self.individual.hpo_terms.exists())

    def test_leaving_and_reopening_discards_temporary_selection(self):
        self.post("Ataxia")
        self.post(action="remove", term_id=self.seizure.pk)
        response = self.open_editor()
        self.assertContains(response, f'name="hpo_terms" value="{self.seizure.pk}"')
        self.assertNotContains(response, f'name="hpo_terms" value="{self.ataxia.pk}"')

    def test_draft_search_can_readd_a_removed_saved_term(self):
        from lab.views import HPOTermSearchView
        request = RequestFactory().get(reverse("lab:hpo_picker"), {"q": "Seizure", "individual_id": self.individual.pk, "draft": "1"})
        request.user = self.editor
        response = HPOTermSearchView.as_view()(request)
        self.assertIn(self.seizure, response.context_data["results"])

    def test_unmatched_paste_explained_without_changing_terms(self):
        response = self.post("NoSuchPhenotype\n, ")
        self.assertContains(response, "No matching HPO terms found.")
        self.assertEqual(list(self.individual.hpo_terms.values_list("pk", flat=True)), [self.seizure.pk])

    def test_invalid_selection_cannot_overwrite_saved_terms(self):
        for selected in [["invalid"], ["99999999"]]:
            response = self.post(action="save", selected=selected)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(list(self.individual.hpo_terms.values_list("pk", flat=True)), [self.seizure.pk])

    def test_bulk_add_and_save_require_edit_permission(self):
        from lab.models import Project, ProjectMembership
        viewer = User.objects.create_user(username="phenotype-viewer")
        project = Project.objects.create(name="Phenotype project", created_by=self.editor)
        project.individuals.add(self.individual)
        ProjectMembership.objects.create(project=project, user=viewer, role=ProjectMembership.Role.VIEWER, created_by=self.editor)
        for action in ["bulk_add", "save"]:
            response = self.post("Ataxia", user=viewer, action=action, selected=[self.ataxia.pk])
            self.assertEqual(response.status_code, 403)
        self.assertFalse(self.individual.hpo_terms.filter(pk=self.ataxia.pk).exists())
