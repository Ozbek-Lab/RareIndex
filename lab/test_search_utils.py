from django.contrib.auth.models import User
from django.test import TestCase

from lab.models import Institution
from lab.search_utils import filter_normalized_contains, normalize_search_text, normalized_contains


class TurkishSearchNormalizationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="searchuser", password="password")

    def test_turkish_case_pairs_normalize_together(self):
        self.assertEqual(normalize_search_text("İpek"), normalize_search_text("ipek"))
        self.assertEqual(normalize_search_text("Işık"), normalize_search_text("ışık"))
        self.assertTrue(normalized_contains("İstanbul Üniversitesi", "istanbul"))
        self.assertTrue(normalized_contains("Isparta Merkezi", "ısparta"))

    def test_normalized_queryset_filter_handles_turkish_case(self):
        istanbul = Institution.objects.create(name="İstanbul Üniversitesi", created_by=self.user)
        isparta = Institution.objects.create(name="Isparta Merkezi", created_by=self.user)

        dotted_i_results = filter_normalized_contains(
            Institution.objects.all(),
            ["name"],
            "istanbul",
        )
        dotless_i_results = filter_normalized_contains(
            Institution.objects.all(),
            ["name"],
            "ısparta",
        )

        self.assertQuerySetEqual(dotted_i_results, [istanbul], transform=lambda obj: obj)
        self.assertQuerySetEqual(dotless_i_results, [isparta], transform=lambda obj: obj)
