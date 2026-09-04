from django.test import TestCase

from lab.management.commands._import_helpers import get_hpo_terms
from ontologies.models import Ontology, Term


class ImportHPOParsingTests(TestCase):
    def setUp(self):
        self.ontology = Ontology.objects.create(type=1, label="HP")
        self.terms = [
            Term.objects.create(
                ontology=self.ontology,
                identifier=identifier,
                label=label,
            )
            for identifier, label in (
                ("0001263", "Global developmental delay"),
                ("0000252", "Microcephaly"),
                ("0000533", "Chorioretinal atrophy"),
                ("0000365", "Hearing impairment"),
                ("0000639", "Nystagmus"),
                ("0004322", "Short stature"),
            )
        ]

    def test_embedded_comma_separated_hpo_codes_are_extracted(self):
        value = (
            "Global developmental delay HP:0001263, Microcephaly HP:0000252, "
            "Chorioretinal atrophy HP:0000533, Hearing impairment HP:0000365, "
            "Nystagmus HP:0000639, Short stature HP:0004322"
        )

        terms = get_hpo_terms(value)

        self.assertEqual(
            [term.identifier for term in terms],
            [
                "0001263",
                "0000252",
                "0000533",
                "0000365",
                "0000639",
                "0004322",
            ],
        )

    def test_hpo_codes_are_deduplicated_preserving_order(self):
        terms = get_hpo_terms("HP:0001263\nHP:1263, HP:0000252")

        self.assertEqual(
            [term.identifier for term in terms],
            ["0001263", "0000252"],
        )
