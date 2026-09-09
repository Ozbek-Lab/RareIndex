from django.contrib.auth.models import User
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import QueryDict
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from lab.consanguinity import CONSANGUINITY_CHOICES
from lab.filters import IndividualFilter, VariantFilter
from lab.forms import CreateFamilyForm, FamilyConfigForm
from lab.htmx_views import family_id_edit, family_id_save
from lab.models import Family, Individual
from variant.models import Variant


class FamilyConsanguinityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(username="consanguinity-admin")
        cls.people = {}
        for index, (value, _) in enumerate(CONSANGUINITY_CHOICES):
            family = Family.objects.create(family_id=f"F-{index}", is_consanguineous=value, created_by=cls.user)
            individual = Individual.objects.create(family=family, created_by=cls.user)
            cls.people[value] = individual
            Variant.objects.create(individual=individual, chromosome="chr1", start=index, end=index, created_by=cls.user)
        cls.no_family = Individual.objects.create(created_by=cls.user)
        Variant.objects.create(individual=cls.no_family, chromosome="chr1", start=99, end=99, created_by=cls.user)

    def test_family_forms_save_all_choices(self):
        for form_class in (CreateFamilyForm, FamilyConfigForm):
            for index, (value, label) in enumerate(CONSANGUINITY_CHOICES):
                with self.subTest(form=form_class.__name__, choice=value):
                    form = form_class(data={"family_id": f"{form_class.__name__}-{index}", "is_consanguineous": value or ""})
                    self.assertTrue(form.is_valid(), form.errors)
                    family = form.save(commit=False)
                    family.created_by = self.user
                    family.save()
                    family.refresh_from_db()
                    self.assertEqual(family.is_consanguineous, value)
                    self.assertEqual(family.get_is_consanguineous_display(), label)
                    self.assertEqual(family.history.first().is_consanguineous, value)

    def test_inline_editor_saves_new_choices_and_rejects_invalid_values(self):
        family = self.people[None].family
        factory = RequestFactory()
        for value, label in [("same_village", "Same Village"), ("nearby_villages", "Nearby Villages")]:
            request = factory.post(reverse("lab:family_id_save", args=[family.pk]), {"family_id": family.family_id, "is_consanguineous": value})
            request.user = self.user
            response = family_id_save(request, family.pk)
            self.assertContains(response, label)
            family.refresh_from_db()
            self.assertEqual(family.is_consanguineous, value)
            request = factory.get(reverse("lab:family_id_edit", args=[family.pk]))
            request.user = self.user
            response = family_id_edit(request, family.pk)
            self.assertContains(response, f"value: '{value}'")
            self.assertContains(response, "Same Village")
            self.assertContains(response, "Nearby Villages")
        request = factory.post("/", {"family_id": family.family_id, "is_consanguineous": "invalid"})
        request.user = self.user
        self.assertContains(family_id_save(request, family.pk), "Select a valid consanguinity option.")
        family.refresh_from_db()
        self.assertEqual(family.is_consanguineous, "nearby_villages")

    def assert_filter_matches(self, data, expected):
        query = QueryDict(mutable=True)
        for key, value in data.items():
            query.setlist(key, value if isinstance(value, list) else [value])
        for filter_class, model, field in [(IndividualFilter, Individual, "pk"), (VariantFilter, Variant, "individual_id")]:
            with self.subTest(filter=filter_class.__name__, data=data):
                filters = filter_class(data=query, queryset=model.objects.all())
                self.assertTrue(filters.is_valid(), filters.errors)
                self.assertCountEqual(filters.qs.values_list(field, flat=True), expected)

    def test_individual_and_variant_filters_distinguish_all_options(self):
        field = "family__is_consanguineous"
        for value, person in self.people.items():
            expected = [person.pk] + ([self.no_family.pk] if value is None else [])
            self.assert_filter_matches({field: value or "unknown"}, expected)
        selected = ["same_village", "nearby_villages"]
        self.assert_filter_matches({field: selected}, [self.people[value].pk for value in selected])
        self.assert_filter_matches({field: selected, field + "__mode": "all"}, [])
        self.assert_filter_matches({field: selected, field + "__exclude": "same_village"}, [self.people["nearby_villages"].pk])
        excluded = {field + "__exclude": "same_village", "filter_group_mode": "any"}
        self.assert_filter_matches(excluded, [person.pk for value, person in self.people.items() if value != "same_village"] + [self.no_family.pk])

    def test_badges_display_village_choices_without_consanguineous_label(self):
        for value, label in CONSANGUINITY_CHOICES:
            html = render_to_string("lab/components/consanguinity_badge.html", {"family": self.people[value].family, "show_unknown": True})
            self.assertIn(label, html)
            self.assertEqual("badge-warning" in html, value == "true")

    def test_legacy_boolean_assignments_remain_compatible(self):
        family = self.people[None].family
        for original, expected in [(True, "true"), (False, "false"), (None, None)]:
            family.is_consanguineous = original
            family.save()
            family.refresh_from_db()
            self.assertEqual(family.is_consanguineous, expected)

    def test_import_recognizes_village_options(self):
        from lab.management.commands.import_all import normalize_consanguinity_value
        for original, expected in [(True, "true"), (False, "false"), ("Unknown", None), ("Same Village", "same_village"), ("Nearby Villages", "nearby_villages")]:
            self.assertEqual(normalize_consanguinity_value(original), expected)


class FamilyConsanguinityMigrationTests(TransactionTestCase):
    old_target = [("lab", "0003_historicalprojectmembership_projectmembership")]
    new_target = [("lab", "0004_family_consanguinity_choices")]

    def test_migration_preserves_existing_families_and_history(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.old_target)
        try:
            apps = executor.loader.project_state(self.old_target).apps
            user = apps.get_model("auth", "User").objects.create(username="migration-user")
            old_family = apps.get_model("lab", "Family")
            old_history = apps.get_model("lab", "HistoricalFamily")
            for index, value in enumerate((True, False, None)):
                family = old_family.objects.create(family_id=f"M-{index}", created_by_id=user.pk, is_consanguineous=value)
                old_history.objects.create(id=family.pk, family_id=family.family_id, created_by_id=user.pk, is_consanguineous=value, history_date=timezone.now(), history_type="+")
            executor = MigrationExecutor(connection)
            executor.migrate(self.new_target)
            apps = executor.loader.project_state(self.new_target).apps
            for name in ("Family", "HistoricalFamily"):
                self.assertEqual(list(apps.get_model("lab", name).objects.order_by("family_id").values_list("is_consanguineous", flat=True)), ["true", "false", None])
        finally:
            MigrationExecutor(connection).migrate(self.new_target)
