from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from lab.models import Family, Institution, Individual

User = get_user_model()


class MapVisualizationViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="mapuser", password="password")
        self.client.login(username="mapuser", password="password")

        self.istanbul = Institution.objects.create(
            name="Istanbul Center",
            city="Istanbul",
            created_by=self.user,
        )
        self.ankara = Institution.objects.create(
            name="Ankara Center",
            city="Ankara",
            created_by=self.user,
        )
        self.izmir = Institution.objects.create(
            name="Izmir Center",
            city="Izmir",
            created_by=self.user,
        )

        self.family = Family.objects.create(
            family_id="F-001",
            created_by=self.user,
        )

        self.individual_1 = Individual.objects.create(
            full_name="Index Person",
            created_by=self.user,
            family=self.family,
            is_index=True,
        )
        self.individual_1.institution.add(self.istanbul)

        self.individual_2 = Individual.objects.create(
            full_name="Sibling Person",
            created_by=self.user,
            family=self.family,
            is_index=False,
        )
        self.individual_2.institution.add(self.istanbul)

        self.individual_3 = Individual.objects.create(
            full_name="Familyless Index",
            created_by=self.user,
            is_index=True,
        )
        self.individual_3.institution.add(self.ankara)

        self.individual_4 = Individual.objects.create(
            full_name="Familyless Non-Index",
            created_by=self.user,
            is_index=False,
        )
        self.individual_4.institution.add(self.izmir)

    def test_map_context_includes_all_city_counts(self):
        response = self.client.get(reverse("lab:map_visualization"), secure=True)
        self.assertEqual(response.status_code, 200)

        rows = response.context["city_rows"]
        self.assertEqual([row["city"] for row in rows], ["Istanbul", "Ankara", "Izmir"])

        istanbul = rows[0]
        ankara = rows[1]
        izmir = rows[2]

        self.assertEqual(istanbul["individuals"], 2)
        self.assertEqual(istanbul["families"], 1)
        self.assertEqual(istanbul["probands"], 1)

        self.assertEqual(ankara["individuals"], 1)
        self.assertEqual(ankara["families"], 1)
        self.assertEqual(ankara["probands"], 1)

        self.assertEqual(izmir["individuals"], 1)
        self.assertEqual(izmir["families"], 1)
        self.assertEqual(izmir["probands"], 0)

        self.assertContains(response, "Individuals")
        self.assertContains(response, "Families")
        self.assertContains(response, "Probands")
