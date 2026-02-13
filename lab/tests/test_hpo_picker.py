from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from ontologies.models import Term, Ontology

class HpoPickerTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpassword")
        self.client.force_login(self.user)
        self.ontology = Ontology.objects.create(name="HPO", type=1) # 1=HP
        self.term = Term.objects.create(ontology=self.ontology, term="HP:0001234", label="Test Abnormality")

    def test_hpo_picker_template(self):
        """Verify the picker returns the simplified template with Alpine bindings."""
        url = reverse('lab:hpo_picker')
        response = self.client.get(url, {'q': 'Test'}, HTTP_HX_REQUEST='true')
        
        self.assertEqual(response.status_code, 200)
        # Check for Alpine click handler
        self.assertContains(response, "@click=\"addHpoTerm")
        self.assertContains(response, "'HP:0001234'")
        # Ensure we DON'T see the sidebar wrapper from the main search
        self.assertNotContains(response, "id=\"hpo-results-list\"")
