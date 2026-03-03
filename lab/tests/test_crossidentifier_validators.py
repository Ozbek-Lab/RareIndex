from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from lab.models import (
    Family,
    Individual,
    Institution,
    Status,
    IdentifierType,
    CrossIdentifier,
)


class CrossIdentifierValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpassword")
        self.institution = Institution.objects.create(name="Test Inst", created_by=self.user)
        self.status = Status.objects.create(name="Active", created_by=self.user)
        self.family = Family.objects.create(family_id="FAM-1", created_by=self.user)
        self.individual = Individual.objects.create(
            full_name="Person One",
            family=self.family,
            status=self.status,
            created_by=self.user,
        )
        self.individual.institution.add(self.institution)

        self.rb_type = IdentifierType.objects.create(
            name="RareBoost",
            description="RareBoost",
            created_by=self.user,
            use_priority=1,
        )
        self.biobank_type = IdentifierType.objects.create(
            name="Biobank",
            description="Biobank",
            created_by=self.user,
            use_priority=2,
        )

    def test_rareboost_id_valid_examples(self):
        xid = CrossIdentifier(
            individual=self.individual,
            id_type=self.rb_type,
            id_value="RB_2025_01.2",
            created_by=self.user,
        )
        xid.full_clean()

        xid2 = CrossIdentifier(
            individual=self.individual,
            id_type=self.rb_type,
            id_value="RB_2025_01.1.3",
            created_by=self.user,
        )
        xid2.full_clean()

    def test_rareboost_id_rejects_missing_final_segment(self):
        xid = CrossIdentifier(
            individual=self.individual,
            id_type=self.rb_type,
            id_value="RB_2025_01.1",
            created_by=self.user,
        )
        with self.assertRaises(ValidationError):
            xid.full_clean()

    def test_biobank_id_valid_examples(self):
        xid = CrossIdentifier(
            individual=self.individual,
            id_type=self.biobank_type,
            id_value="RD3.F12.2",
            created_by=self.user,
        )
        xid.full_clean()

        xid2 = CrossIdentifier(
            individual=self.individual,
            id_type=self.biobank_type,
            id_value="RD3.F12.1.3",
            created_by=self.user,
        )
        xid2.full_clean()

    def test_biobank_id_rejects_missing_final_segment(self):
        xid = CrossIdentifier(
            individual=self.individual,
            id_type=self.biobank_type,
            id_value="RD3.F12.1",
            created_by=self.user,
        )
        with self.assertRaises(ValidationError):
            xid.full_clean()

