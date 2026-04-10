from django.contrib.auth import get_user_model
from django.test import TestCase

from lab.management.commands._import_helpers import (
    build_id_map,
    find_individual_by_rareboost_id,
    normalize_id,
)
from lab.models import CrossIdentifier, Family, IdentifierType, Individual

User = get_user_model()


class RareBoostImportIdResolutionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="testpass")
        self.family = Family.objects.create(family_id="FAM-1", created_by=self.user)
        self.rb_type = IdentifierType.objects.create(
            name="RareBoost",
            description="RareBoost",
            created_by=self.user,
            use_priority=1,
        )

        self.ind_variant = Individual.objects.create(
            full_name="Variant One",
            family=self.family,
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.ind_variant,
            id_type=self.rb_type,
            id_value="RB_2026_1.1.1",
            created_by=self.user,
        )

        self.ind_legacy = Individual.objects.create(
            full_name="Legacy One",
            family=self.family,
            created_by=self.user,
        )
        CrossIdentifier.objects.create(
            individual=self.ind_legacy,
            id_type=self.rb_type,
            id_value="RB_2026_2.1",
            created_by=self.user,
        )

    def test_find_individual_by_rareboost_id_accepts_renumbered_variants(self):
        self.assertEqual(
            find_individual_by_rareboost_id("RB_2026_1.1").id,
            self.ind_variant.id,
        )
        self.assertEqual(
            find_individual_by_rareboost_id("RB_2026_2.1.1").id,
            self.ind_legacy.id,
        )

    def test_build_id_map_includes_aliases_for_import_lookup(self):
        id_map = build_id_map()

        self.assertEqual(
            id_map[normalize_id("RB_2026_1.1")].id,
            self.ind_variant.id,
        )
        self.assertEqual(
            id_map[normalize_id("RB_2026_1.1.1")].id,
            self.ind_variant.id,
        )
        self.assertEqual(
            id_map[normalize_id("RB_2026_2.1")].id,
            self.ind_legacy.id,
        )
        self.assertEqual(
            id_map[normalize_id("RB_2026_2.1.1")].id,
            self.ind_legacy.id,
        )
