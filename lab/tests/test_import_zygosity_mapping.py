from django.test import SimpleTestCase

from lab.management.commands.import_all import _map_zygosity_strict, _normalize_yayin_zygosity
from lab.management.commands._import_helpers import map_zygosity


class ImportZygosityMappingTests(SimpleTestCase):
    def test_import_all_strict_zygocity_accepts_turkish_labels(self):
        samples = {
            "Heterozigot": "het",
            "Homozigot": "hom",
            "Hemizigot": "hemi",
            "Heteroplazmi": "hetpl",
            "Homoplazmi": "homoplasmy",
            "NA": "unknown",
            "n/a": "unknown",
        }

        for raw, expected in samples.items():
            with self.subTest(raw=raw):
                self.assertEqual(_map_zygosity_strict(raw), expected)

    def test_yayin_ici_zygosity_accepts_turkish_labels(self):
        samples = {
            "Heterozigot": "het",
            "Homozigot": "hom",
            "Hemizigot": "hemi",
            "Heteroplazmi": "hetpl",
            "Homoplazmi": "homoplasmy",
            "NA": "unknown",
        }

        for raw, expected in samples.items():
            with self.subTest(raw=raw):
                self.assertEqual(_normalize_yayin_zygosity(raw), expected)

    def test_shared_helper_zygosity_mapper_accepts_turkish_labels(self):
        samples = {
            "Heterozigot": "het",
            "Homozigot": "hom",
            "Hemizigot": "hemi",
            "Heteroplazmi": "hetpl",
            "Homoplazmi": "homoplasmy",
            "NA": "unknown",
        }

        for raw, expected in samples.items():
            with self.subTest(raw=raw):
                self.assertEqual(map_zygosity(raw), expected)
