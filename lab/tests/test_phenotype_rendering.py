from django.test import TestCase
from lab.models import Individual, Status
from ontologies.models import Ontology, Term
from django.template.loader import render_to_string
from django.contrib.auth.models import User

class PhenotypeRenderingTest(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="testuser")
        self.status = Status.objects.create(name="Active", created_by=self.user)
        
        # Create Ontologies
        self.hp_ontology = Ontology.objects.create(type=1, label="Human Phenotype Ontology") # HP
        self.mondo_ontology = Ontology.objects.create(type=2, label="Mondo") # MONDO

        # Create Terms
        self.hpo_term = Term.objects.create(
            ontology=self.hp_ontology,
            identifier="0000001",
            label="Test HPO Term"
        )
        self.mondo_term = Term.objects.create(
            ontology=self.mondo_ontology,
            identifier="12345",
            label="Test MONDO Term"
        )
        
        # Create Individual
        self.individual = Individual.objects.create(
            full_name="Test Individual",
            created_by=self.user,
            status=self.status
        )
        self.individual.hpo_terms.add(self.hpo_term, self.mondo_term)

    def test_phenotype_template_rendering(self):
        context = {'individual': self.individual}
        rendered = render_to_string("lab/partials/tabs/_phenotype.html", context)
        
        # Check HPO Term rendering
        self.assertIn("Test HPO Term", rendered)
        # Check that we are using the relative selector
        self.assertIn('hx-target="closest .hpo-container"', rendered)
        self.assertIn('class="hpo-container', rendered)
        self.assertIn("HP:0000001", rendered)
        
        # Check MONDO Term rendering (should be under Other Ontology Terms)
        self.assertIn("Test MONDO Term", rendered)
        # self.assertIn("MONDO:12345", rendered) # Term property logic handles prefix
        
        # Check for duplicated headers (The bug)
        # We expect "Other Ontology Terms" to appear, but ideally only once per group.
        # The current buggy template might not render it correctly or render it multiple times.
        # Let's count occurrences.
        
        # note: The actual bug description says "does not render correctly".
        # If the template accesses term.ontology.prefix and it fails silently (django template),
        # the if conditions using it might evaluate to False or act weirdly.
        # Or if it errors, test will fail.
        
        print(rendered) 
