from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.contrib.auth.models import User
from ontologies.models import Term, Ontology
from lab.views import HPOTermSearchView, IndividualListView

class HPOSearchTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.factory = RequestFactory()
        
        # Create Ontology
        self.ontology = Ontology.objects.create(type=1, label="HPO")
        
        # Create Terms
        self.term1 = Term.objects.create(ontology=self.ontology, identifier="0000001", label="All")
        self.term2 = Term.objects.create(ontology=self.ontology, identifier="0001250", label="Seizure")
        self.term3 = Term.objects.create(ontology=self.ontology, identifier="0001257", label="Spasticity")

    def test_search_view(self):
        """Test that the search view returns matching HPO terms."""
        request = self.factory.get(reverse('lab:hpo_search'), {'q': 'Seiz'})
        request.user = self.user
        request.htmx = True
        
        view = HPOTermSearchView.as_view()
        response = view(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.term2, response.context_data['results'])
        self.assertNotIn(self.term3, response.context_data['results'])

    def test_search_view_exclusion(self):
        """Test that selected terms are excluded from search results."""
        # Search for 'Seiz' but exclude term2 (Seizure)
        request = self.factory.get(reverse('lab:hpo_search'), {'q': 'Seiz', 'hpo_terms': [self.term2.pk]})
        request.user = self.user
        request.htmx = True
        
        view = HPOTermSearchView.as_view()
        response = view(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context_data['results'].exists())

    def test_render_selected_term_trigger(self):
        """Test that rendering a selected term triggers the filter-changed event."""
        from lab.views import RenderSelectedHPOTermView
        request = self.factory.get(reverse('lab:render_selected_hpo', kwargs={'pk': self.term2.pk}))
        request.user = self.user
        
        view = RenderSelectedHPOTermView.as_view()
        response = view(request, pk=self.term2.pk)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['HX-Trigger'], 'filter-changed')

    def test_search_view_empty_query(self):
        """Test that empty query returns no results."""
        request = self.factory.get(reverse('lab:hpo_search'), {'q': ''})
        request.user = self.user
        request.htmx = True
        
        view = HPOTermSearchView.as_view()
        response = view(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context_data['results'].exists())

    def test_individual_list_context_optimization(self):
        """Test that the list view does NOT load the full tree anymore."""
        request = self.factory.get(reverse('lab:individual_list'))
        request.user = self.user
        request.htmx = False # Mock HTMX middleware
        
        view = IndividualListView.as_view()
        response = view(request)
        
        # Check 'hpo_tree' is NOT in context
        self.assertNotIn('hpo_tree', response.context_data)
        
    def test_individual_list_selected_terms(self):
        """Test that selected terms are correctly loaded into context."""
        request = self.factory.get(reverse('lab:individual_list'), {'hpo_terms': [self.term2.pk]})
        request.user = self.user
        request.htmx = False # Mock HTMX middleware
        
        view = IndividualListView.as_view()
        response = view(request)
        
        self.assertIn(self.term2, response.context_data['selected_hpo_terms'])
        self.assertNotIn(self.term3, response.context_data['selected_hpo_terms'])

    def test_search_view_picker_variant(self):
        """Test that the picker variant returns the correct partial and Alpine.js logic."""
        request = self.factory.get(reverse('lab:hpo_search'), {'q': 'Seiz', 'variant': 'picker'})
        request.user = self.user
        request.htmx = True
        
        view = HPOTermSearchView.as_view()
        response = view(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('lab/partials/hpo_search_results_picker.html', response.template_name)
        # Check for Alpine JS logic in content
        response.render()
        self.assertIn(b'@click="addHpoTerm', response.content)
