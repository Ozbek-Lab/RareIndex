from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.contrib.auth.models import User
from ontologies.models import Term, Ontology
from lab.models import Individual
from lab.filters import IndividualFilter

class HPOFilterBugTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.factory = RequestFactory()
        
        # Create Ontology
        self.ontology = Ontology.objects.create(type=1, label="HPO")
        
        # Create Terms
        self.term = Term.objects.create(ontology=self.ontology, identifier="0001250", label="Seizure")
        
        # Create Status
        from lab.models import Status
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(Individual)
        self.status = Status.objects.create(name="Active", content_type=ct, created_by=self.user)
        
        # Create Individual with this term
        self.ind = Individual.objects.create(full_name="Test Individual", status=self.status, created_by=self.user)
        self.ind.hpo_terms.add(self.term)

    def test_filter_with_obo_id(self):
        """Test filtering with 'HP:0001250' string."""
        data = {'hpo_terms': ['HP:0001250']}
        f = IndividualFilter(data=data, queryset=Individual.objects.all())
        
        if not f.is_valid():
            self.fail(f"Filter is invalid: {f.errors}")
            
        qs = f.qs
        self.assertEqual(qs.count(), 1, "Should find the individual with Seizure")
        self.assertEqual(qs.first(), self.ind)

    def test_filter_with_pk(self):
        """Test filtering with PK (integer)."""
        data = {'hpo_terms': [str(self.term.id)]}
        f = IndividualFilter(data=data, queryset=Individual.objects.all())
        
        if not f.is_valid():
            self.fail(f"Filter is invalid: {f.errors}")
            
        qs = f.qs
        self.assertEqual(qs.count(), 1)
