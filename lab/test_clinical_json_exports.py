import json
from datetime import date

from django.contrib.auth.models import Permission, User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from lab.models import CrossIdentifier, IdentifierType, Individual, Sample, SampleType
from lab.views import (
    IndividualDetailView,
    IndividualFHIRExportView,
    IndividualPhenopacketExportView,
)
from ontologies.models import Ontology, Term


class IndividualClinicalJsonExportTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="exporter", password="password")
        self.view_permission = Permission.objects.get(codename="view_individual")
        self.sensitive_permission = Permission.objects.get(codename="view_sensitive_data")
        self.user.user_permissions.add(self.view_permission, self.sensitive_permission)

        self.ontology = Ontology.objects.create(type=1, label="2024-01-01")
        self.hpo_term = Term.objects.create(
            ontology=self.ontology,
            identifier="0001250",
            label="Seizure",
            description="A seizure phenotype.",
        )
        self.identifier_type = IdentifierType.objects.create(
            name="Study ID",
            use_priority=1,
            created_by=self.user,
        )
        self.sample_type = SampleType.objects.create(name="Blood", created_by=self.user)

        self.individual = Individual.objects.create(
            full_name="John Doe",
            tc_identity=12345678901,
            birth_date=date(2000, 1, 1),
            sex="male",
            is_alive=True,
            is_affected=True,
            diagnosis="Bethlem myopathy",
            icd11_code="8C70.0",
            diagnosis_date=date(2024, 1, 2),
            age_of_onset_in_months=168,
            created_by=self.user,
        )
        self.individual.hpo_terms.add(self.hpo_term)
        CrossIdentifier.objects.create(
            individual=self.individual,
            id_type=self.identifier_type,
            id_value="RI-001",
            created_by=self.user,
        )
        Sample.objects.create(
            individual=self.individual,
            sample_type=self.sample_type,
            receipt_date=date(2024, 2, 3),
            sample_measurements="OD 1.8",
            created_by=self.user,
        )

    def test_info_tab_shows_json_export_buttons(self):
        request = self.factory.get(reverse("lab:individual_detail", args=[self.individual.pk]))
        request.user = self.user
        request.htmx = False

        response = IndividualDetailView.as_view()(request, pk=self.individual.pk)
        response.render()
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Export as FHIR", content)
        self.assertIn(reverse("lab:individual_export_fhir", args=[self.individual.pk]), content)
        self.assertIn("Export as Phenopacket", content)
        self.assertIn(reverse("lab:individual_export_phenopacket", args=[self.individual.pk]), content)
        self.assertEqual(content.count('hx-boost="false"'), 2)
        self.assertEqual(content.count("download"), 2)

    def test_info_tab_shows_disabled_json_export_buttons_without_both_permissions(self):
        users = [
            User.objects.create_user(username="viewonly", password="password"),
            User.objects.create_user(username="sensitiveonly", password="password"),
        ]
        users[0].user_permissions.add(self.view_permission)
        users[1].user_permissions.add(self.sensitive_permission)

        for user in users:
            request = self.factory.get(reverse("lab:individual_detail", args=[self.individual.pk]))
            request.user = user
            request.htmx = False

            response = IndividualDetailView.as_view()(request, pk=self.individual.pk)
            response.render()
            content = response.content.decode()

            self.assertIn("Export as FHIR", content)
            self.assertIn("Export as Phenopacket", content)
            self.assertEqual(content.count('aria-disabled="true"'), 2)
            self.assertNotIn(reverse("lab:individual_export_fhir", args=[self.individual.pk]), content)
            self.assertNotIn(reverse("lab:individual_export_phenopacket", args=[self.individual.pk]), content)

    def test_fhir_export_downloads_bundle(self):
        request = self.factory.get(reverse("lab:individual_export_fhir", args=[self.individual.pk]))
        request.user = self.user

        response = IndividualFHIRExportView.as_view()(request, pk=self.individual.pk)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/fhir+json"))
        self.assertIn(f"individual-{self.individual.pk}.fhir.json", response["Content-Disposition"])
        self.assertEqual(data["resourceType"], "Bundle")
        self.assertEqual(data["type"], "collection")

        resources = [entry["resource"] for entry in data["entry"]]
        patient = next(resource for resource in resources if resource["resourceType"] == "Patient")
        self.assertEqual(patient["gender"], "male")
        self.assertEqual(patient["birthDate"], "2000-01-01")
        self.assertEqual(patient["name"][0]["text"], "John Doe")
        self.assertEqual(patient["identifier"][0]["value"], "RI-001")

        condition = next(resource for resource in resources if resource["resourceType"] == "Condition")
        self.assertEqual(condition["code"]["coding"][0]["code"], "8C70.0")
        self.assertEqual(condition["onsetAge"]["value"], 168)

        observation = next(resource for resource in resources if resource["resourceType"] == "Observation")
        self.assertEqual(observation["code"]["coding"][0]["code"], "HP:0001250")

        specimen = next(resource for resource in resources if resource["resourceType"] == "Specimen")
        self.assertEqual(specimen["type"]["text"], "Blood")

    def test_fhir_export_requires_both_individual_view_and_sensitive_permissions(self):
        limited_user = User.objects.create_user(username="limited", password="password")
        view_only_user = User.objects.create_user(username="viewonly-export", password="password")
        sensitive_only_user = User.objects.create_user(username="sensitiveonly-export", password="password")
        view_only_user.user_permissions.add(self.view_permission)
        sensitive_only_user.user_permissions.add(self.sensitive_permission)

        for user in [limited_user, view_only_user, sensitive_only_user]:
            request = self.factory.get(reverse("lab:individual_export_fhir", args=[self.individual.pk]))
            request.user = user

            response = IndividualFHIRExportView.as_view()(request, pk=self.individual.pk)

            self.assertEqual(response.status_code, 403)

    def test_phenopacket_export_requires_both_individual_view_and_sensitive_permissions(self):
        limited_user = User.objects.create_user(username="limited-phenopacket", password="password")
        view_only_user = User.objects.create_user(username="viewonly-phenopacket", password="password")
        sensitive_only_user = User.objects.create_user(username="sensitiveonly-phenopacket", password="password")
        view_only_user.user_permissions.add(self.view_permission)
        sensitive_only_user.user_permissions.add(self.sensitive_permission)

        for user in [limited_user, view_only_user, sensitive_only_user]:
            request = self.factory.get(
                reverse("lab:individual_export_phenopacket", args=[self.individual.pk])
            )
            request.user = user

            response = IndividualPhenopacketExportView.as_view()(request, pk=self.individual.pk)

            self.assertEqual(response.status_code, 403)

    def test_phenopacket_export_downloads_schema_v2_json(self):
        request = self.factory.get(reverse("lab:individual_export_phenopacket", args=[self.individual.pk]))
        request.user = self.user

        response = IndividualPhenopacketExportView.as_view()(request, pk=self.individual.pk)
        data = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/json"))
        self.assertIn(
            f"individual-{self.individual.pk}.phenopacket.json",
            response["Content-Disposition"],
        )
        self.assertEqual(data["subject"]["sex"], "MALE")
        self.assertEqual(data["subject"]["dateOfBirth"], "2000-01-01T00:00:00Z")
        self.assertEqual(data["phenotypicFeatures"][0]["type"]["id"], "HP:0001250")
        self.assertEqual(data["diseases"][0]["term"]["id"], "ICD11:8C70.0")
        self.assertEqual(data["diseases"][0]["onset"]["age"]["iso8601duration"], "P14Y")
        self.assertEqual(data["biosamples"][0]["sampleType"]["label"], "Blood")
        self.assertEqual(data["metaData"]["phenopacketSchemaVersion"], "2.0")
        self.assertIn(
            "hp",
            {resource["id"] for resource in data["metaData"]["resources"]},
        )
