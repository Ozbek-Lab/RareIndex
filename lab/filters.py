import django_filters
from django import forms
from django.db.models import Count, Exists, OuterRef, Q
from django.contrib.contenttypes.models import ContentType
from .models import (
    Individual, Sample, Project, SampleType, TestType, Status, PipelineType,
    Institution, Test, Pipeline, Analysis, AnalysisType, TaggedStatus, Family,
)
from .search_utils import filter_normalized_contains, normalized_contains, normalized_contains_q
from variant.models import ACMGEvidenceOverride, Variant, Annotation
from variant.templatetags.variant_filters import ACMG_CRITERIA_INFO

FILTER_MODE_SUFFIX = "__mode"
FILTER_MODE_ANY = "any"
FILTER_MODE_ALL = "all"
FILTER_MODE_TOGETHER = "together"
FILTER_GROUP_MODE_ANY = "any"

def _request_targets_table(request, target_id):
    return bool(
        getattr(request, "htmx", False)
        and getattr(request, "headers", {}).get("HX-Target") == target_id
    )


def _values_for_data(data, field_name):
    if hasattr(data, "getlist"):
        return [value for value in data.getlist(field_name) if value != ""]
    value = data.get(field_name) if data else None
    if not value:
        return []
    return value if isinstance(value, list) else [value]


def _submitted_choice_values(data, *field_names):
    values = []
    seen = set()
    for field_name in field_names:
        for key in (field_name, f"{field_name}__exclude"):
            for value in _values_for_data(data, key):
                if value not in seen:
                    values.append(value)
                    seen.add(value)
    return [(value, value) for value in values]


def _get_filter_mode(data, field_name, allow_together=False):
    if not data:
        return FILTER_MODE_ANY
    raw = data.get(f"{field_name}{FILTER_MODE_SUFFIX}", FILTER_MODE_ANY)
    allowed = {FILTER_MODE_ANY, FILTER_MODE_ALL}
    if allow_together:
        allowed.add(FILTER_MODE_TOGETHER)
    return raw if raw in allowed else FILTER_MODE_ANY


def _filter_lookup_values(queryset, lookup_base, values, mode):
    if not values:
        return queryset
    if mode in {FILTER_MODE_ALL, FILTER_MODE_TOGETHER}:
        for item in values:
            queryset = queryset.filter(**{lookup_base: item})
        return queryset
    return queryset.filter(**{f"{lookup_base}__in": values})


def _exclude_values_for_data(data, field_name):
    exclude_key = f"{field_name}__exclude"
    if hasattr(data, "getlist"):
        return [value for value in data.getlist(exclude_key) if value != ""]
    value = data.get(exclude_key) if data else None
    if not value:
        return []
    return value if isinstance(value, list) else [value]


def _matching_tagged_object_ids(model_class, status_values, mode=FILTER_MODE_ANY):
    ct = ContentType.objects.get_for_model(model_class)
    qs = TaggedStatus.objects.filter(content_type=ct, tag__in=status_values)
    if mode in {FILTER_MODE_ALL, FILTER_MODE_TOGETHER} and status_values:
        status_ids = [getattr(status, "pk", status) for status in status_values]
        return (
            qs.values("object_id")
            .annotate(matched_statuses=Count("tag_id", distinct=True))
            .filter(matched_statuses=len(set(status_ids)))
            .values_list("object_id", flat=True)
        )
    return qs.values_list("object_id", flat=True)


class TristateFilterMixin:
    """
    Mixin to add exclusion logic to a MultipleChoiceFilter or ModelMultipleChoiceFilter.
    Expects the query params:
      - field_name=value (for inclusion)
      - field_name__exclude=value (for exclusion)
    """
    def filter(self, queryset, value):
        
        # 1. Handle Inclusion (standard behavior)
        if value:
            mode = FILTER_MODE_ANY
            if self.parent:
                mode = _get_filter_mode(self.parent.data, self.field_name, allow_together=True)
            lookup_base = self.field_name
            queryset = _filter_lookup_values(queryset, lookup_base, value, mode)

        if not self.parent:
            return queryset.distinct()

        # Get the underlying data (QueryDict)
        data = self.parent.data

        # 2. Handle Exclusion
        # We look for the key with '__exclude' suffix
        exclude_key = f"{self.field_name}__exclude"
        
        if hasattr(data, 'getlist'):
            excluded_values = data.getlist(exclude_key)
        else:
            excluded_values = data.get(exclude_key, [])
            if not isinstance(excluded_values, list):
                excluded_values = [excluded_values]
        
        if excluded_values:
             # Exclude logic
            lookup_field = self.field_name
            # Check for to_field_name in extra kwargs
            to_field_name = self.extra.get('to_field_name')
            if to_field_name:
                lookup_field = f"{self.field_name}__{to_field_name}"
            
            lookup = f"{lookup_field}__in"
            queryset = queryset.exclude(**{lookup: excluded_values})
            
        return queryset.distinct()

class TristateMultipleChoiceFilter(TristateFilterMixin, django_filters.MultipleChoiceFilter):
    pass

class TristateModelMultipleChoiceFilter(TristateFilterMixin, django_filters.ModelMultipleChoiceFilter):
    pass

class FamilyConsanguinityFilter(TristateMultipleChoiceFilter):
    def filter(self, queryset, value):
        if not self.parent or not self.parent.data:
            return queryset.distinct()

        data = self.parent.data

        def values_for(key):
            if hasattr(data, "getlist"):
                return [item for item in data.getlist(key) if item != ""]
            raw = data.get(key, [])
            if not isinstance(raw, list):
                raw = [raw]
            return [item for item in raw if item != ""]

        def build_query(values):
            query = Q()
            known_values = []
            if "true" in values:
                known_values.append(True)
            if "false" in values:
                known_values.append(False)
            if known_values:
                query |= Q(family__is_consanguineous__in=known_values)
            if "unknown" in values:
                query |= (
                    Q(family__isnull=True) |
                    Q(family__is_consanguineous__isnull=True)
                )
            return query

        selected_values = values_for(self.field_name)
        excluded_values = values_for(f"{self.field_name}__exclude")

        if selected_values:
            mode = _get_filter_mode(data, self.field_name)
            if mode == FILTER_MODE_ALL and len(set(selected_values)) > 1:
                queryset = queryset.none()
            else:
                queryset = queryset.filter(build_query(selected_values))

        if excluded_values:
            queryset = queryset.exclude(build_query(excluded_values))

        return queryset.distinct()

class OpenMultipleChoiceField(forms.MultipleChoiceField):
    def valid_value(self, value):
        return True

class OpenMultipleChoiceFilter(django_filters.MultipleChoiceFilter):
    field_class = OpenMultipleChoiceField

def _filter_by_tagged_status(queryset, model_class, status_values, exclude=False):
    """
    Filter a queryset by statuses applied via TaggedStatus.
    status_values: queryset or list of Status instances.
    """
    matched_ids = _matching_tagged_object_ids(model_class, status_values)
    if exclude:
        return queryset.exclude(pk__in=matched_ids)
    return queryset.filter(pk__in=matched_ids)


def _filter_related_by_tagged_status(queryset, related_model_class, relation_path, status_values, exclude=False):
    """
    Filter a queryset by statuses on a related model (e.g. Individual filtered by Sample statuses).
    relation_path: ORM path from the root model to the related model (e.g. 'samples').
    """
    ct = ContentType.objects.get_for_model(related_model_class)
    matched_related_ids = TaggedStatus.objects.filter(
        content_type=ct,
        tag__in=status_values,
    ).values_list("object_id", flat=True)
    lookup = f"{relation_path}__in"
    if exclude:
        return queryset.exclude(**{lookup: matched_related_ids})
    return queryset.filter(**{lookup: matched_related_ids})


def _acmg_evidence_choices():
    catalog_codes = list(ACMG_CRITERIA_INFO)
    stored_codes = (
        ACMGEvidenceOverride.objects.exclude(criterion="")
        .values_list("criterion", flat=True)
        .distinct()
    )
    codes = []
    seen = set()
    for code in [*catalog_codes, *stored_codes]:
        normalized = str(code or "").strip().replace(" ", "_").upper()
        if normalized and normalized not in seen:
            codes.append(normalized)
            seen.add(normalized)
    return [(code, code) for code in codes]


def _filter_acmg_evidence_values(queryset, relation_path, values, mode):
    if not values:
        return queryset
    lookup_base = f"{relation_path}__criterion"
    included_lookup = f"{relation_path}__included"
    if mode in {FILTER_MODE_ALL, FILTER_MODE_TOGETHER}:
        for value in values:
            queryset = queryset.filter(**{lookup_base: value, included_lookup: True})
        return queryset
    return queryset.filter(**{f"{lookup_base}__in": values, included_lookup: True})


def _format_annotation_choice_label(value):
    return str(value).replace("_", " ").replace("-", " ").title()


def _annotation_acmg_classification_choices():
    values = set()
    for lookup in ("data__variants__0__acmg_classification", "data__acmg_classification"):
        values.update(
            value
            for value in Annotation.objects.filter(source__icontains="genebe")
            .exclude(**{f"{lookup}__isnull": True})
            .exclude(**{lookup: ""})
            .values_list(lookup, flat=True)
            if value
        )
    return [(value, _format_annotation_choice_label(value)) for value in sorted(values)]


def _annotation_acmg_classification_q(relation_path, values):
    if not values:
        return Q()
    return Q(
        **{
            f"{relation_path}__source__icontains": "genebe",
            f"{relation_path}__data__variants__0__acmg_classification__in": values,
        }
    ) | Q(
        **{
            f"{relation_path}__source__icontains": "genebe",
            f"{relation_path}__data__acmg_classification__in": values,
        }
    )


def _filter_annotation_acmg_classification_values(queryset, relation_path, values, mode):
    if not values:
        return queryset
    if mode in {FILTER_MODE_ALL, FILTER_MODE_TOGETHER}:
        for value in values:
            queryset = queryset.filter(_annotation_acmg_classification_q(relation_path, [value]))
        return queryset
    return queryset.filter(_annotation_acmg_classification_q(relation_path, values))


class IndividualFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method='filter_search', label="Search")

    # Individual Fields
    status = TristateModelMultipleChoiceFilter(
        queryset=Status.objects.all(),
        to_field_name='name',
        method='filter_individual_status',
        label="Individual Status",
    )
    sex = TristateMultipleChoiceFilter(choices=Individual._meta.get_field('sex').choices)
    is_alive = TristateMultipleChoiceFilter(choices=[(True, 'Alive'), (False, 'Deceased')])
    is_affected = TristateMultipleChoiceFilter(choices=[(True, 'Affected'), (False, 'Unaffected')])
    is_index = TristateMultipleChoiceFilter(choices=[(True, 'Yes'), (False, 'No')], label="Is Index")
    age_of_onset_months_min = django_filters.NumberFilter(
        field_name="age_of_onset_in_months",
        lookup_expr="gte",
        label="Minimum Age of Onset (months)",
    )
    age_of_onset_months_max = django_filters.NumberFilter(
        field_name="age_of_onset_in_months",
        lookup_expr="lte",
        label="Maximum Age of Onset (months)",
    )
    family__is_consanguineous = FamilyConsanguinityFilter(
        choices=[
            ("false", "Non-Consanguineous"),
            ("unknown", "Unknown"),
            ("true", "Consanguineous"),
        ],
        label="Family Consanguinity",
    )

    # Sample Fields
    samples__status = TristateModelMultipleChoiceFilter(
        queryset=Status.objects.all(),
        to_field_name='name',
        method='filter_sample_status',
        label="Sample Status",
    )
    samples__sample_type = TristateModelMultipleChoiceFilter(
        queryset=SampleType.objects.all(),
        to_field_name='name',
        method='filter_sample_type',
        label="Sample Type",
    )

    # Test Fields
    samples__tests__status = TristateModelMultipleChoiceFilter(
        queryset=Status.objects.all(),
        to_field_name='name',
        method='filter_test_status',
        label="Test Status",
    )
    samples__tests__test_type = TristateModelMultipleChoiceFilter(
        queryset=TestType.objects.all(),
        to_field_name='name',
        method='filter_test_type',
        label="Test Type",
    )

    # Pipeline Fields
    samples__tests__pipelines__status = TristateModelMultipleChoiceFilter(
        queryset=Status.objects.all(),
        to_field_name='name',
        method='filter_pipeline_status',
        label="Pipeline Status",
    )
    samples__tests__pipelines__type = TristateModelMultipleChoiceFilter(
        queryset=PipelineType.objects.all(),
        to_field_name='name',
        method='filter_pipeline_type',
        label="Pipeline Type",
    )

    # Analysis Fields
    samples__tests__pipelines__analyses__status = TristateModelMultipleChoiceFilter(
        queryset=Status.objects.all(),
        to_field_name='name',
        method='filter_analysis_status',
        label="Analysis Status",
    )
    samples__tests__pipelines__analyses__type = TristateModelMultipleChoiceFilter(
        queryset=AnalysisType.objects.all(),
        to_field_name='name',
        method='filter_analysis_type',
        label="Analysis Type",
    )

    # Variant Fields
    variants__status = TristateModelMultipleChoiceFilter(
        queryset=Status.objects.all(),
        to_field_name='name',
        method='filter_variant_status',
        label="Variant Status",
    )
    # Note: Variant 'type' is a property, not a field, so we can't filter directly easily 
    # unless we annotate or it's stored. Looking at models.py, SNV/CNV/etc are subclasses.
    # We might need a custom method for variant type if it's strictly about the python property.
    # However, standard Django filters work on database fields. 
    # The user asked for "variant types". 
    # Let's check if we can filter by the subclass existence or if there is a discriminatory field.
    # The models are multi-table inheritance. 
    # We can filter by `variants__snv__isnull=False` for SNV, etc.
    # For now, I will add a custom method filter for Variant Type.
    variant_type = django_filters.MultipleChoiceFilter(
        choices=[
            ('SNV', 'SNV'), ('CNV', 'CNV'), ('SV', 'SV'), ('Repeat', 'Repeat')
        ],
        method='filter_variant_type',
        label="Variant Type"
    )

    variants__annotation_acmg_classification = django_filters.MultipleChoiceFilter(
        choices=[],
        method="filter_variant_annotation_acmg_classification",
        label="ACMG Classification",
    )
    variants__acmg_evidence = django_filters.MultipleChoiceFilter(
        choices=[],
        method="filter_variant_acmg_evidence",
        label="ACMG Evidence",
    )

    has_report = django_filters.MultipleChoiceFilter(
        choices=[('true', 'Yes'), ('false', 'No')],
        method='filter_has_report',
        label="Has Report",
    )
    has_request_form = django_filters.MultipleChoiceFilter(
        choices=[('true', 'Yes'), ('false', 'No')],
        method='filter_has_request_form',
        label="Has Request Form",
    )
    projects = django_filters.MultipleChoiceFilter(
        field_name='projects__name',
        choices=[],
        method='filter_projects',
        label="Project",
    )
    
    # Institution filters (all go through the M2M Individual.institution)
    institution_name = django_filters.CharFilter(
        method='filter_institution_name',
        label="Institution Name",
    )
    institution__city = TristateMultipleChoiceFilter(
        choices=[],  # populated in __init__
        label="Institution City",
    )
    institution__speciality = TristateMultipleChoiceFilter(
        choices=[],  # populated in __init__
        label="Institution Speciality",
    )
    institution__center_name = TristateMultipleChoiceFilter(
        choices=[],  # populated in __init__
        label="Institution Center",
    )

    # HPO Terms (Many-to-Many)
    # HPO Terms (Many-to-Many)
    # HPO Terms (Many-to-Many)
    hpo_terms = OpenMultipleChoiceFilter(
        choices=[], # Dynamically populated in __init__
        label="HPO Terms",
        method='filter_hpo_terms'
    )

    def filter_hpo_terms(self, queryset, name, value):
        from ontologies.utils import get_descendants, get_descendants_from_obo
        
        # 1. Handle Inclusion (OR logic for now, or keep existing logic)
        # Existing logic: individuals who have ANY of these terms
        if value:
            mode = _get_filter_mode(self.data, name)
            term_groups = []

            for selected_value in value:
                selected_db_ids = set()
                selected_obo_ids = set()
                try:
                    selected_db_ids.add(int(selected_value))
                except (ValueError, TypeError):
                    selected_obo_ids.add(str(selected_value))

                relevant_term_ids = set()
                if selected_db_ids:
                    relevant_term_ids.update(get_descendants(selected_db_ids))
                if selected_obo_ids:
                    relevant_term_ids.update(get_descendants_from_obo(selected_obo_ids))
                if relevant_term_ids:
                    term_groups.append(relevant_term_ids)

            if mode == FILTER_MODE_ALL:
                for term_ids in term_groups:
                    queryset = queryset.filter(hpo_terms__in=term_ids)
            else:
                all_relevant_term_ids = set()
                for term_ids in term_groups:
                    all_relevant_term_ids.update(term_ids)
                queryset = queryset.filter(hpo_terms__in=all_relevant_term_ids)

        # 2. Handle Exclusion
        data = self.data
        if hasattr(data, 'getlist'):
            excluded_values = data.getlist(f"{name}__exclude")
        else:
            excluded_values = data.get(f"{name}__exclude", [])
            if not isinstance(excluded_values, list):
                excluded_values = [excluded_values]
        
        if excluded_values:
            ex_db_ids = set()
            ex_obo_ids = set()
            for v in excluded_values:
                try:
                    ex_db_ids.add(int(v))
                except (ValueError, TypeError):
                    ex_obo_ids.add(str(v))
            
            ex_term_ids = set()
            if ex_db_ids:
                ex_term_ids.update(get_descendants(ex_db_ids))
            if ex_obo_ids:
                ex_term_ids.update(get_descendants_from_obo(ex_obo_ids))
                
            if ex_term_ids:
                queryset = queryset.exclude(hpo_terms__in=ex_term_ids)

        return queryset.distinct()

    class Meta:
        model = Individual
        fields = ['sex', 'family']

    def filter_institution_name(self, queryset, name, value):
        if value:
            queryset = filter_normalized_contains(queryset, ["institution__name"], value)
        return queryset.distinct()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        table_only_request = _request_targets_table(
            getattr(self, "request", None),
            "individual-table-container",
        )
        if 'hpo_terms' in self.filters:
            from ontologies.models import Term
            self.filters['hpo_terms'].queryset = Term.objects.all()

        if table_only_request:
            city_choices = _submitted_choice_values(self.data, "institution__city")
            speciality_choices = _submitted_choice_values(self.data, "institution__speciality")
            center_choices = _submitted_choice_values(self.data, "institution__center_name")
            project_choices = _submitted_choice_values(self.data, "projects")
            annotation_classification_choices = _submitted_choice_values(
                self.data,
                "variants__annotation_acmg_classification",
            )
            acmg_evidence_choices = _submitted_choice_values(
                self.data,
                "variants__acmg_evidence",
            )
        else:
            # Populate dynamic choices for institution sub-filters
            city_choices = [
                (v, v) for v in
                Institution.objects.exclude(city__isnull=True).exclude(city='')
                .values_list('city', flat=True).distinct().order_by('city')
            ]
            speciality_choices = [
                (v, v) for v in
                Institution.objects.exclude(speciality__isnull=True).exclude(speciality='')
                .values_list('speciality', flat=True).distinct().order_by('speciality')
            ]
            center_choices = [
                (v, v) for v in
                Institution.objects.exclude(center_name__isnull=True).exclude(center_name='')
                .values_list('center_name', flat=True).distinct().order_by('center_name')
            ]
            
            project_choices = [
                (name, name) for name in Project.objects.values_list('name', flat=True).order_by('name')
            ]
            annotation_classification_choices = _annotation_acmg_classification_choices()
            acmg_evidence_choices = _acmg_evidence_choices()

        self.filters['institution__city'].field.choices = city_choices
        self.filters['institution__speciality'].field.choices = speciality_choices
        self.filters['institution__center_name'].field.choices = center_choices
        self.filters['projects'].field.choices = project_choices

        # Restrict Status filter querysets by ContentType
        self._restrict_status_queryset('status', Individual)
        self._restrict_status_queryset('samples__status', Sample)
        self._restrict_status_queryset('samples__tests__status', Test)
        self._restrict_status_queryset('samples__tests__pipelines__status', Pipeline)
        self._restrict_status_queryset('samples__tests__pipelines__analyses__status', Analysis)
        self._restrict_status_queryset('variants__status', Variant)
        self.filters["variants__annotation_acmg_classification"].field.choices = annotation_classification_choices
        self.filters["variants__acmg_evidence"].field.choices = acmg_evidence_choices

    def _restrict_status_queryset(self, field_name, model_class):
        if field_name in self.filters:
            ct = ContentType.objects.get_for_model(model_class)
            self.filters[field_name].queryset = (
                Status.objects.filter(content_type=ct)
                .select_related("group")
                .order_by("group__name", "name")
            )

    # --- Custom method filters for status fields (TaggedStatus/GenericFK based) ---

    def _filter_exists(self, queryset, related_queryset):
        return queryset.filter(Exists(related_queryset.values("pk")[:1]))

    def _exclude_exists(self, queryset, related_queryset):
        return queryset.exclude(Exists(related_queryset.values("pk")[:1]))

    def _apply_exists_values(self, queryset, related_queryset_factory, values, mode):
        if not values:
            return queryset
        values = list(values)
        if mode in {FILTER_MODE_ALL, FILTER_MODE_TOGETHER}:
            for value in values:
                queryset = self._filter_exists(queryset, related_queryset_factory([value]))
            return queryset
        return self._filter_exists(queryset, related_queryset_factory(values))

    def _get_exclude_statuses(self, field_name, model_class):
        """Return a Status queryset for the excluded values in the __exclude param."""
        data = self.data
        exclude_key = f"{field_name}__exclude"
        if hasattr(data, 'getlist'):
            excluded_names = data.getlist(exclude_key)
        else:
            excluded_names = data.get(exclude_key, [])
            if not isinstance(excluded_names, list):
                excluded_names = [excluded_names] if excluded_names else []
        if excluded_names:
            return Status.objects.filter(name__in=excluded_names)
        return Status.objects.none()

    def filter_individual_status(self, queryset, name, value):
        mode = _get_filter_mode(self.data, 'status')
        if value:
            matched_ids = _matching_tagged_object_ids(Individual, value, mode)
            queryset = queryset.filter(pk__in=matched_ids)
        excluded = self._get_exclude_statuses('status', Individual)
        if excluded.exists():
            queryset = _filter_by_tagged_status(queryset, Individual, excluded, exclude=True)
        return queryset.distinct()

    def filter_sample_status(self, queryset, name, value):
        mode = _get_filter_mode(self.data, 'samples__status', allow_together=True)
        if value:
            sample_ids = _matching_tagged_object_ids(Sample, value, mode)
            sample_qs = Sample.objects.filter(
                individual_id=OuterRef("pk"),
                pk__in=sample_ids,
            )
            queryset = self._filter_exists(queryset, sample_qs)
        excluded = self._get_exclude_statuses('samples__status', Sample)
        if excluded.exists():
            excl_sample_ids = _matching_tagged_object_ids(Sample, excluded)
            sample_qs = Sample.objects.filter(
                individual_id=OuterRef("pk"),
                pk__in=excl_sample_ids,
            )
            queryset = self._exclude_exists(queryset, sample_qs)
        return queryset.distinct()

    def filter_sample_type(self, queryset, name, value):
        mode = _get_filter_mode(self.data, name, allow_together=True)
        queryset = self._apply_exists_values(
            queryset,
            lambda values: Sample.objects.filter(
                individual_id=OuterRef("pk"),
                sample_type__in=values,
            ),
            value,
            mode,
        )
        excluded_values = self._exclude_values_for(name)
        if excluded_values:
            queryset = self._exclude_exists(
                queryset,
                Sample.objects.filter(
                    individual_id=OuterRef("pk"),
                    sample_type__name__in=excluded_values,
                ),
            )
        return queryset.distinct()

    def filter_test_status(self, queryset, name, value):
        mode = _get_filter_mode(self.data, 'samples__tests__status', allow_together=True)
        if value:
            test_ids = _matching_tagged_object_ids(Test, value, mode)
            test_qs = Test.objects.filter(
                sample__individual_id=OuterRef("pk"),
                pk__in=test_ids,
            )
            queryset = self._filter_exists(queryset, test_qs)
        excluded = self._get_exclude_statuses('samples__tests__status', Test)
        if excluded.exists():
            excl_ids = _matching_tagged_object_ids(Test, excluded)
            test_qs = Test.objects.filter(
                sample__individual_id=OuterRef("pk"),
                pk__in=excl_ids,
            )
            queryset = self._exclude_exists(queryset, test_qs)
        return queryset.distinct()

    def filter_test_type(self, queryset, name, value):
        mode = _get_filter_mode(self.data, name, allow_together=True)
        queryset = self._apply_exists_values(
            queryset,
            lambda values: Test.objects.filter(
                sample__individual_id=OuterRef("pk"),
                test_type__in=values,
            ),
            value,
            mode,
        )
        excluded_values = self._exclude_values_for(name)
        if excluded_values:
            queryset = self._exclude_exists(
                queryset,
                Test.objects.filter(
                    sample__individual_id=OuterRef("pk"),
                    test_type__name__in=excluded_values,
                ),
            )
        return queryset.distinct()

    def filter_pipeline_status(self, queryset, name, value):
        mode = _get_filter_mode(self.data, 'samples__tests__pipelines__status', allow_together=True)
        if value:
            pipe_ids = _matching_tagged_object_ids(Pipeline, value, mode)
            pipeline_qs = Pipeline.objects.filter(
                test__sample__individual_id=OuterRef("pk"),
                pk__in=pipe_ids,
            )
            queryset = self._filter_exists(queryset, pipeline_qs)
        excluded = self._get_exclude_statuses('samples__tests__pipelines__status', Pipeline)
        if excluded.exists():
            excl_ids = _matching_tagged_object_ids(Pipeline, excluded)
            pipeline_qs = Pipeline.objects.filter(
                test__sample__individual_id=OuterRef("pk"),
                pk__in=excl_ids,
            )
            queryset = self._exclude_exists(queryset, pipeline_qs)
        return queryset.distinct()

    def filter_pipeline_type(self, queryset, name, value):
        mode = _get_filter_mode(self.data, name, allow_together=True)
        queryset = self._apply_exists_values(
            queryset,
            lambda values: Pipeline.objects.filter(
                test__sample__individual_id=OuterRef("pk"),
                type__in=values,
            ),
            value,
            mode,
        )
        excluded_values = self._exclude_values_for(name)
        if excluded_values:
            queryset = self._exclude_exists(
                queryset,
                Pipeline.objects.filter(
                    test__sample__individual_id=OuterRef("pk"),
                    type__name__in=excluded_values,
                ),
            )
        return queryset.distinct()

    def filter_analysis_status(self, queryset, name, value):
        mode = _get_filter_mode(self.data, 'samples__tests__pipelines__analyses__status', allow_together=True)
        if value:
            analysis_ids = _matching_tagged_object_ids(Analysis, value, mode)
            analysis_qs = Analysis.objects.filter(
                pipeline__test__sample__individual_id=OuterRef("pk"),
                pk__in=analysis_ids,
            )
            queryset = self._filter_exists(queryset, analysis_qs)
        excluded = self._get_exclude_statuses('samples__tests__pipelines__analyses__status', Analysis)
        if excluded.exists():
            excl_ids = _matching_tagged_object_ids(Analysis, excluded)
            analysis_qs = Analysis.objects.filter(
                pipeline__test__sample__individual_id=OuterRef("pk"),
                pk__in=excl_ids,
            )
            queryset = self._exclude_exists(queryset, analysis_qs)
        return queryset.distinct()

    def filter_analysis_type(self, queryset, name, value):
        mode = _get_filter_mode(self.data, name, allow_together=True)
        queryset = self._apply_exists_values(
            queryset,
            lambda values: Analysis.objects.filter(
                pipeline__test__sample__individual_id=OuterRef("pk"),
                type__in=values,
            ),
            value,
            mode,
        )
        excluded_values = self._exclude_values_for(name)
        if excluded_values:
            queryset = self._exclude_exists(
                queryset,
                Analysis.objects.filter(
                    pipeline__test__sample__individual_id=OuterRef("pk"),
                    type__name__in=excluded_values,
                ),
            )
        return queryset.distinct()

    def filter_variant_status(self, queryset, name, value):
        mode = _get_filter_mode(self.data, 'variants__status', allow_together=True)
        if value:
            variant_ids = _matching_tagged_object_ids(Variant, value, mode)
            queryset = queryset.filter(variants__id__in=variant_ids)
        excluded = self._get_exclude_statuses('variants__status', Variant)
        if excluded.exists():
            excl_ids = _matching_tagged_object_ids(Variant, excluded)
            queryset = queryset.exclude(variants__id__in=excl_ids)
        return queryset.distinct()

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset

        search_query = normalized_contains_q(queryset, ["cross_ids__id_value", "id"], value)
        request_user = getattr(getattr(self, "request", None), "user", None)
        if request_user and request_user.has_perm("lab.view_sensitive_data"):
            matching_name_ids = []
            name_queryset = (
                queryset.prefetch_related(None)
                .only("pk", "full_name")
                .order_by()
            )
            for individual in name_queryset.iterator(chunk_size=1000):
                if normalized_contains(individual.full_name, value):
                    matching_name_ids.append(individual.pk)
            if matching_name_ids:
                search_query |= Q(pk__in=matching_name_ids)
        return queryset.filter(search_query).distinct()

    def filter_variant_type(self, queryset, name, value):
        if not value:
            return queryset
            
        # This one is tricky for simple inclusion/exclusion in the same custom class
        # because it's a method filter. 
        # Let's handle the inclusion logic here manually.
        # Value is a list of selected types strings ['SNV', 'CNV']
        
        # We need to construct a robust query.
        q_obj = Q()
        if 'SNV' in value:
            q_obj |= Q(variants__snv__isnull=False)
        if 'CNV' in value:
            q_obj |= Q(variants__cnv__isnull=False)
        if 'SV' in value:
            q_obj |= Q(variants__sv__isnull=False)
        if 'Repeat' in value:
            q_obj |= Q(variants__repeat__isnull=False)
            
        # Handle Exclusion (checking query params directly)
        data = self.data
        excluded_values = _exclude_values_for_data(data, name)
        
        exclude_q = Q()
        if 'SNV' in excluded_values:
            exclude_q |= Q(variants__snv__isnull=False)
        if 'CNV' in excluded_values:
            exclude_q |= Q(variants__cnv__isnull=False)
        if 'SV' in excluded_values:
            exclude_q |= Q(variants__sv__isnull=False)
        if 'Repeat' in excluded_values:
            exclude_q |= Q(variants__repeat__isnull=False)
            
        mode = _get_filter_mode(self.data, name, allow_together=True)
        if value:
            if mode in {FILTER_MODE_ALL, FILTER_MODE_TOGETHER}:
                for variant_type in value:
                    if variant_type == 'SNV':
                        queryset = queryset.filter(variants__snv__isnull=False)
                    elif variant_type == 'CNV':
                        queryset = queryset.filter(variants__cnv__isnull=False)
                    elif variant_type == 'SV':
                        queryset = queryset.filter(variants__sv__isnull=False)
                    elif variant_type == 'Repeat':
                        queryset = queryset.filter(variants__repeat__isnull=False)
            else:
                queryset = queryset.filter(q_obj)
        if excluded_values:
            queryset = queryset.exclude(exclude_q)
            
        return queryset.distinct()

    def filter_variant_acmg_evidence(self, queryset, name, value):
        mode = _get_filter_mode(self.data, name, allow_together=True)
        queryset = _filter_acmg_evidence_values(
            queryset,
            "variants__acmg_evidence_overrides",
            value,
            mode,
        )

        excluded_values = self._exclude_values_for(name)
        if excluded_values:
            queryset = queryset.exclude(
                variants__acmg_evidence_overrides__criterion__in=excluded_values,
                variants__acmg_evidence_overrides__included=True,
            )

        return queryset.distinct()

    def filter_variant_annotation_acmg_classification(self, queryset, name, value):
        mode = _get_filter_mode(self.data, name)
        queryset = _filter_annotation_acmg_classification_values(
            queryset,
            "variants__annotations",
            value,
            mode,
        )

        excluded_values = self._exclude_values_for(name)
        if excluded_values:
            queryset = queryset.exclude(
                _annotation_acmg_classification_q("variants__annotations", excluded_values)
            )

        return queryset.distinct()

    def filter_has_report(self, queryset, name, value):
        values = set(value or [])
        mode = _get_filter_mode(self.data, name)
        if not values or values == {'true', 'false'} and mode == FILTER_MODE_ANY:
            return queryset
        if values == {'true', 'false'}:
            return queryset.none()
        if 'true' in values:
            return queryset.filter(samples__tests__pipelines__analyses__reports__isnull=False).distinct()
        if 'false' in values:
            return queryset.filter(samples__tests__pipelines__analyses__reports__isnull=True).distinct()
        return queryset

    def filter_has_request_form(self, queryset, name, value):
        values = set(value or [])
        mode = _get_filter_mode(self.data, name)
        if not values or values == {'true', 'false'} and mode == FILTER_MODE_ANY:
            return queryset
        if values == {'true', 'false'}:
            return queryset.none()
        if 'true' in values:
            return queryset.filter(analysis_request_forms__isnull=False).distinct()
        if 'false' in values:
            return queryset.filter(analysis_request_forms__isnull=True).distinct()
        return queryset

    def filter_projects(self, queryset, name, value):
        mode = _get_filter_mode(self.data, name, allow_together=True)
        if not value:
            return queryset
        if mode in {FILTER_MODE_ALL, FILTER_MODE_TOGETHER}:
            for project_name in value:
                queryset = queryset.filter(projects__name=project_name)
            return queryset.distinct()
        return queryset.filter(projects__name__in=value).distinct()

    def filter_queryset(self, queryset):
        if self.data.get("filter_group_mode") == FILTER_GROUP_MODE_ANY:
            return self._filter_queryset_any_group(queryset)
        search_value = self.form.cleaned_data.get("search")
        for name, value in self.form.cleaned_data.items():
            if name == "search":
                continue
            queryset = self.filters[name].filter(queryset, value)
        queryset = self._apply_together_constraints(queryset)
        queryset = self._apply_variant_acmg_evidence_exclusions(queryset).distinct()
        if search_value:
            queryset = self.filters["search"].filter(queryset, search_value)
        return queryset.distinct()

    def _filter_queryset_any_group(self, queryset):
        base_queryset = queryset
        search_value = self.form.cleaned_data.get("search")
        base_queryset = self._apply_global_exclusions(base_queryset)

        combined_queryset = queryset.none()
        has_include_group = False

        for name, filter_instance in self.filters.items():
            if name == "search":
                continue
            value = self.form.cleaned_data.get(name)
            if self._is_empty_filter_value(value):
                continue

            has_include_group = True
            filtered_group = filter_instance.filter(base_queryset, value)
            filtered_group = self._apply_together_constraints_for_fields(filtered_group, [name])
            combined_queryset = combined_queryset | filtered_group

        if not has_include_group:
            result_queryset = base_queryset.distinct()
        else:
            result_queryset = combined_queryset.distinct()

        if search_value:
            result_queryset = self.filters["search"].filter(result_queryset, search_value)

        return result_queryset.distinct()

    def _is_empty_filter_value(self, value):
        if value is None or value == "":
            return True
        if hasattr(value, "exists"):
            return not value.exists()
        try:
            return len(value) == 0
        except TypeError:
            return False

    def _exclude_values_for(self, field_name):
        return _exclude_values_for_data(self.data, field_name)

    def _apply_variant_acmg_evidence_exclusions(self, queryset):
        excluded_values = self._exclude_values_for("variants__acmg_evidence")
        if not excluded_values:
            return queryset
        return queryset.exclude(
            variants__acmg_evidence_overrides__criterion__in=excluded_values,
            variants__acmg_evidence_overrides__included=True,
        )

    def _apply_variant_annotation_acmg_classification_exclusions(self, queryset):
        excluded_values = self._exclude_values_for("variants__annotation_acmg_classification")
        if not excluded_values:
            return queryset
        return queryset.exclude(
            _annotation_acmg_classification_q("variants__annotations", excluded_values)
        )

    def _apply_global_exclusions(self, queryset):
        for name in self.filters:
            excluded_values = self._exclude_values_for(name)
            if not excluded_values:
                continue
            if name == "variants__annotation_acmg_classification":
                queryset = self._apply_variant_annotation_acmg_classification_exclusions(queryset)
                continue
            if name == "variants__acmg_evidence":
                queryset = self._apply_variant_acmg_evidence_exclusions(queryset)
                continue

            field_queryset = queryset.model.objects.all()
            field = self.filters[name].field
            empty_value = getattr(field, "empty_value", None)
            if empty_value is None:
                empty_value = [] if isinstance(field, forms.MultipleChoiceField) else ""
            excluded_queryset = self.filters[name].filter(field_queryset, empty_value)
            queryset = queryset.exclude(pk__in=excluded_queryset.values("pk"))

        queryset = self._apply_variant_acmg_evidence_exclusions(queryset)
        queryset = self._apply_variant_annotation_acmg_classification_exclusions(queryset)
        return queryset.distinct()

    def _values_for(self, field_name):
        if hasattr(self.data, "getlist"):
            return [value for value in self.data.getlist(field_name) if value != ""]
        value = self.data.get(field_name)
        if not value:
            return []
        return value if isinstance(value, list) else [value]

    def _section_uses_together(self, field_names):
        return any(
            _get_filter_mode(self.data, field_name, allow_together=True) == FILTER_MODE_TOGETHER
            for field_name in field_names
        )

    def _apply_model_values(self, queryset, lookup_base, values, mode):
        if not values:
            return queryset
        if mode in {FILTER_MODE_ALL, FILTER_MODE_TOGETHER}:
            for value in values:
                queryset = queryset.filter(**{lookup_base: value})
            return queryset
        return queryset.filter(**{f"{lookup_base}__in": values})

    def _apply_status_values_to_related_qs(self, related_qs, model_class, status_names, mode):
        if not status_names:
            return related_qs
        status_values = Status.objects.filter(name__in=status_names)
        matched_ids = _matching_tagged_object_ids(model_class, status_values, mode)
        return related_qs.filter(pk__in=matched_ids)

    def _apply_variant_type_values(self, queryset, values, mode, prefix=""):
        if not values:
            return queryset
        lookups = {
            'SNV': f'{prefix}snv__isnull',
            'CNV': f'{prefix}cnv__isnull',
            'SV': f'{prefix}sv__isnull',
            'Repeat': f'{prefix}repeat__isnull',
        }
        if mode in {FILTER_MODE_ALL, FILTER_MODE_TOGETHER}:
            for variant_type in values:
                lookup = lookups.get(variant_type)
                if lookup:
                    queryset = queryset.filter(**{lookup: False})
            return queryset
        q_obj = Q()
        for variant_type in values:
            lookup = lookups.get(variant_type)
            if lookup:
                q_obj |= Q(**{lookup: False})
        return queryset.filter(q_obj)

    def _apply_together_constraints(self, queryset):
        return self._apply_together_constraints_for_fields(queryset, None)

    def _apply_together_constraints_for_fields(self, queryset, active_fields=None):
        active_fields = set(active_fields) if active_fields is not None else None

        def fields_are_active(field_names):
            return active_fields is None or bool(active_fields.intersection(field_names))

        institution_fields = ['institution__city', 'institution__speciality', 'institution__center_name']
        if fields_are_active(institution_fields) and self._section_uses_together(institution_fields):
            institution_qs = Institution.objects.all()
            city_values = self._values_for('institution__city')
            city_mode = _get_filter_mode(self.data, 'institution__city', allow_together=True)
            institution_qs = self._apply_model_values(institution_qs, 'city', city_values, city_mode)
            speciality_values = self._values_for('institution__speciality')
            speciality_mode = _get_filter_mode(self.data, 'institution__speciality', allow_together=True)
            institution_qs = self._apply_model_values(institution_qs, 'speciality', speciality_values, speciality_mode)
            center_values = self._values_for('institution__center_name')
            center_mode = _get_filter_mode(self.data, 'institution__center_name', allow_together=True)
            institution_qs = self._apply_model_values(institution_qs, 'center_name', center_values, center_mode)
            through_qs = Individual.institution.through.objects.filter(
                individual_id=OuterRef("pk"),
                institution_id__in=institution_qs.values("pk"),
            )
            queryset = self._filter_exists(queryset, through_qs)

        sample_fields = ['samples__sample_type', 'samples__status']
        if fields_are_active(sample_fields) and self._section_uses_together(sample_fields):
            sample_qs = Sample.objects.filter(individual_id=OuterRef("pk"))
            sample_type_values = self._values_for('samples__sample_type')
            sample_type_mode = _get_filter_mode(self.data, 'samples__sample_type', allow_together=True)
            sample_qs = self._apply_model_values(sample_qs, 'sample_type__name', sample_type_values, sample_type_mode)
            sample_status_values = self._values_for('samples__status')
            sample_status_mode = _get_filter_mode(self.data, 'samples__status', allow_together=True)
            sample_qs = self._apply_status_values_to_related_qs(sample_qs, Sample, sample_status_values, sample_status_mode)
            queryset = self._filter_exists(queryset, sample_qs)

        test_fields = ['samples__tests__test_type', 'samples__tests__status']
        if fields_are_active(test_fields) and self._section_uses_together(test_fields):
            test_qs = Test.objects.filter(sample__individual_id=OuterRef("pk"))
            test_type_values = self._values_for('samples__tests__test_type')
            test_type_mode = _get_filter_mode(self.data, 'samples__tests__test_type', allow_together=True)
            test_qs = self._apply_model_values(test_qs, 'test_type__name', test_type_values, test_type_mode)
            test_status_values = self._values_for('samples__tests__status')
            test_status_mode = _get_filter_mode(self.data, 'samples__tests__status', allow_together=True)
            test_qs = self._apply_status_values_to_related_qs(test_qs, Test, test_status_values, test_status_mode)
            queryset = self._filter_exists(queryset, test_qs)

        pipeline_fields = ['samples__tests__pipelines__type', 'samples__tests__pipelines__status']
        if fields_are_active(pipeline_fields) and self._section_uses_together(pipeline_fields):
            pipeline_qs = Pipeline.objects.filter(test__sample__individual_id=OuterRef("pk"))
            pipeline_type_values = self._values_for('samples__tests__pipelines__type')
            pipeline_type_mode = _get_filter_mode(self.data, 'samples__tests__pipelines__type', allow_together=True)
            pipeline_qs = self._apply_model_values(pipeline_qs, 'type__name', pipeline_type_values, pipeline_type_mode)
            pipeline_status_values = self._values_for('samples__tests__pipelines__status')
            pipeline_status_mode = _get_filter_mode(self.data, 'samples__tests__pipelines__status', allow_together=True)
            pipeline_qs = self._apply_status_values_to_related_qs(pipeline_qs, Pipeline, pipeline_status_values, pipeline_status_mode)
            queryset = self._filter_exists(queryset, pipeline_qs)

        analysis_fields = ['samples__tests__pipelines__analyses__type', 'samples__tests__pipelines__analyses__status']
        if fields_are_active(analysis_fields) and self._section_uses_together(analysis_fields):
            analysis_qs = Analysis.objects.filter(pipeline__test__sample__individual_id=OuterRef("pk"))
            analysis_type_values = self._values_for('samples__tests__pipelines__analyses__type')
            analysis_type_mode = _get_filter_mode(self.data, 'samples__tests__pipelines__analyses__type', allow_together=True)
            analysis_qs = self._apply_model_values(analysis_qs, 'type__name', analysis_type_values, analysis_type_mode)
            analysis_status_values = self._values_for('samples__tests__pipelines__analyses__status')
            analysis_status_mode = _get_filter_mode(self.data, 'samples__tests__pipelines__analyses__status', allow_together=True)
            analysis_qs = self._apply_status_values_to_related_qs(analysis_qs, Analysis, analysis_status_values, analysis_status_mode)
            queryset = self._filter_exists(queryset, analysis_qs)

        variant_fields = [
            'variant_type',
            'variants__status',
            'variants__annotation_acmg_classification',
            'variants__acmg_evidence',
        ]
        if fields_are_active(variant_fields) and self._section_uses_together(variant_fields):
            variant_qs = Variant.objects.filter(individual_id=OuterRef("pk"))
            variant_type_values = self._values_for('variant_type')
            variant_type_mode = _get_filter_mode(self.data, 'variant_type', allow_together=True)
            variant_qs = self._apply_variant_type_values(variant_qs, variant_type_values, variant_type_mode)
            variant_status_values = self._values_for('variants__status')
            variant_status_mode = _get_filter_mode(self.data, 'variants__status', allow_together=True)
            variant_qs = self._apply_status_values_to_related_qs(variant_qs, Variant, variant_status_values, variant_status_mode)
            classification_values = self._values_for('variants__annotation_acmg_classification')
            classification_mode = _get_filter_mode(self.data, 'variants__annotation_acmg_classification')
            variant_qs = _filter_annotation_acmg_classification_values(
                variant_qs,
                "annotations",
                classification_values,
                classification_mode,
            )
            evidence_values = self._values_for('variants__acmg_evidence')
            evidence_mode = _get_filter_mode(self.data, 'variants__acmg_evidence', allow_together=True)
            variant_qs = _filter_acmg_evidence_values(
                variant_qs,
                "acmg_evidence_overrides",
                evidence_values,
                evidence_mode,
            )
            queryset = self._filter_exists(queryset, variant_qs)

        queryset = self._apply_variant_annotation_acmg_classification_exclusions(queryset)
        return queryset.distinct()

class VariantFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method='filter_search', label="Search")

    # Core variant fields
    status = TristateModelMultipleChoiceFilter(
        queryset=Status.objects.all(),
        to_field_name='name',
        method='filter_variant_status',
        label="Status",
    )
    zygosity = TristateMultipleChoiceFilter(
        choices=Variant.ZYGOSITY_CHOICES,
        label="Zygosity",
    )
    variant_type = django_filters.MultipleChoiceFilter(
        choices=[('SNV', 'SNV'), ('CNV', 'CNV'), ('SV', 'SV'), ('Repeat', 'Repeat')],
        method='filter_variant_type',
        label="Type",
    )
    annotation_acmg_classification = django_filters.MultipleChoiceFilter(
        choices=[],
        method="filter_annotation_acmg_classification",
        label="ACMG Classification",
    )
    chromosome = django_filters.CharFilter(lookup_expr='icontains', label="Chromosome")
    gene = django_filters.CharFilter(method='filter_gene', label="Gene Symbol")
    assembly_version = TristateMultipleChoiceFilter(
        choices=[],  # populated in __init__
        label="Assembly",
    )

    # Annotation filters
    annotation_source = django_filters.MultipleChoiceFilter(
        choices=[],  # populated in __init__
        method='filter_annotation_source',
        label="Annotation Source",
    )
    acmg_evidence = django_filters.MultipleChoiceFilter(
        choices=[],
        method="filter_acmg_evidence",
        label="ACMG Evidence",
    )
    gnomad_af_max = django_filters.NumberFilter(
        method='filter_gnomad_af_max',
        label="gnomAD AF ≤",
    )

    class Meta:
        model = Variant
        fields = ['zygosity']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        table_only_request = _request_targets_table(
            getattr(self, "request", None),
            "variant-table-container",
        )

        # Restrict Status choices to Variant content type
        ct = ContentType.objects.get_for_model(Variant)
        self.filters['status'].queryset = Status.objects.filter(content_type=ct)

        if table_only_request:
            assembly_choices = _submitted_choice_values(self.data, "assembly_version")
            source_choices = _submitted_choice_values(self.data, "annotation_source")
            annotation_classification_choices = _submitted_choice_values(
                self.data,
                "annotation_acmg_classification",
            )
            acmg_evidence_choices = _submitted_choice_values(self.data, "acmg_evidence")
        else:
            # Dynamically build assembly choices from existing data
            assemblies = (
                Variant.objects.values_list('assembly_version', flat=True)
                .distinct()
                .order_by('assembly_version')
            )
            assembly_choices = [(a, a) for a in assemblies if a]

            # Dynamically build annotation source choices
            sources = (
                Annotation.objects.values_list('source', flat=True)
                .distinct()
                .order_by('source')
            )
            source_choices = [(s, s) for s in sources if s]
            annotation_classification_choices = _annotation_acmg_classification_choices()
            acmg_evidence_choices = _acmg_evidence_choices()

        self.filters['assembly_version'].field.choices = assembly_choices
        self.filters['annotation_source'].field.choices = source_choices
        self.filters["annotation_acmg_classification"].field.choices = annotation_classification_choices
        self.filters["acmg_evidence"].field.choices = acmg_evidence_choices

    def filter_variant_status(self, queryset, name, value):
        variant_ct = ContentType.objects.get_for_model(Variant)
        if value:
            matched_ids = TaggedStatus.objects.filter(
                content_type=variant_ct,
                tag__in=value,
            ).values_list("object_id", flat=True)
            queryset = queryset.filter(pk__in=matched_ids)
        data = self.data
        excluded_names = data.getlist("status__exclude") if hasattr(data, 'getlist') else []
        if excluded_names:
            excl_ids = TaggedStatus.objects.filter(
                content_type=variant_ct,
                tag__name__in=excluded_names,
            ).values_list("object_id", flat=True)
            queryset = queryset.exclude(pk__in=excl_ids)
        return queryset.distinct()

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset

        search_fields = [
            "individual__id",
            "individual__cross_ids__id_value",
            "chromosome",
            "start",
            "end",
            "genes__symbol",
        ]
        request_user = getattr(getattr(self, "request", None), "user", None)
        if request_user and request_user.has_perm("lab.view_sensitive_data"):
            search_fields.append("individual__full_name")

        return filter_normalized_contains(queryset, search_fields, value).distinct()

    def filter_gene(self, queryset, name, value):
        return filter_normalized_contains(queryset, ["genes__symbol"], value).distinct()

    def filter_variant_type(self, queryset, name, value):
        if not value:
            return queryset
        q_obj = Q()
        if 'SNV' in value:
            q_obj |= Q(snv__isnull=False)
        if 'CNV' in value:
            q_obj |= Q(cnv__isnull=False)
        if 'SV' in value:
            q_obj |= Q(sv__isnull=False)
        if 'Repeat' in value:
            q_obj |= Q(repeat__isnull=False)

        data = self.data
        excluded = data.getlist(f"{name}__exclude") if hasattr(data, 'getlist') else []
        exclude_q = Q()
        if 'SNV' in excluded:
            exclude_q |= Q(snv__isnull=False)
        if 'CNV' in excluded:
            exclude_q |= Q(cnv__isnull=False)
        if 'SV' in excluded:
            exclude_q |= Q(sv__isnull=False)
        if 'Repeat' in excluded:
            exclude_q |= Q(repeat__isnull=False)

        if value:
            queryset = queryset.filter(q_obj)
        if excluded:
            queryset = queryset.exclude(exclude_q)
        return queryset.distinct()

    def filter_annotation_source(self, queryset, name, value):
        if not value:
            return queryset
        q = Q()
        for source in value:
            q |= Q(annotations__source=source)
        return queryset.filter(q).distinct()

    def filter_annotation_acmg_classification(self, queryset, name, value):
        mode = _get_filter_mode(self.data, name)
        queryset = _filter_annotation_acmg_classification_values(
            queryset,
            "annotations",
            value,
            mode,
        )

        excluded_values = _exclude_values_for_data(self.data, name)
        if excluded_values:
            queryset = queryset.exclude(
                _annotation_acmg_classification_q("annotations", excluded_values)
            )

        return queryset.distinct()

    def filter_acmg_evidence(self, queryset, name, value):
        mode = _get_filter_mode(self.data, name, allow_together=True)
        queryset = _filter_acmg_evidence_values(
            queryset,
            "acmg_evidence_overrides",
            value,
            mode,
        )

        excluded_values = _exclude_values_for_data(self.data, name)
        if excluded_values:
            queryset = queryset.exclude(
                acmg_evidence_overrides__criterion__in=excluded_values,
                acmg_evidence_overrides__included=True,
            )

        return queryset.distinct()

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        excluded_classifications = _exclude_values_for_data(self.data, "annotation_acmg_classification")
        if excluded_classifications:
            queryset = queryset.exclude(
                _annotation_acmg_classification_q("annotations", excluded_classifications)
            )
        excluded_values = _exclude_values_for_data(self.data, "acmg_evidence")
        if excluded_values:
            queryset = queryset.exclude(
                acmg_evidence_overrides__criterion__in=excluded_values,
                acmg_evidence_overrides__included=True,
            )
        return queryset.distinct()

    def filter_gnomad_af_max(self, queryset, name, value):
        if value is None:
            return queryset
        threshold = float(value)
        # Try the most common JSON paths used by myvariant.info and GeneBe
        annotated_variant_ids = Annotation.objects.filter(
            Q(data__gnomad_genome__af__af__lte=threshold)
            | Q(data__gnomad_exome__af__af__lte=threshold)
            | Q(data__gnomad__af__lte=threshold)
        ).values_list('variant_id', flat=True)
        return queryset.filter(pk__in=annotated_variant_ids).distinct()


class ProjectFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method='filter_search', label="Search")

    # Project Fields
    status = TristateModelMultipleChoiceFilter(
        queryset=Status.objects.all(),
        to_field_name='name',
        method='filter_project_status',
        label="Status",
    )
    priority = TristateMultipleChoiceFilter(choices=[], label="Priority")
    created_by = TristateModelMultipleChoiceFilter(
        queryset=None,
        to_field_name='username',
        label="Created By",
    )

    class Meta:
        model = Project
        fields = ['priority']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Restrict Status choices to Project content type
        ct = ContentType.objects.get_for_model(Project)
        self.filters['status'].queryset = Status.objects.filter(content_type=ct)

        from django.contrib.auth import get_user_model
        User = get_user_model()
        if 'created_by' in self.filters:
            self.filters['created_by'].queryset = User.objects.all()
        
        # Restrict Status choices by ContentType
        self._restrict_status_queryset('status', Project)
        
        # Set priority choices from Task model
        from .models import Task
        if 'priority' in self.filters:
            self.filters['priority'].field.choices = Task.PRIORITY_CHOICES

    def _restrict_status_queryset(self, field_name, model_class):
        if field_name in self.filters:
            ct = ContentType.objects.get_for_model(model_class)
            self.filters[field_name].queryset = Status.objects.filter(content_type=ct)

    def filter_project_status(self, queryset, name, value):
        project_ct = ContentType.objects.get_for_model(Project)
        if value:
            matched_ids = TaggedStatus.objects.filter(
                content_type=project_ct,
                tag__in=value,
            ).values_list("object_id", flat=True)
            queryset = queryset.filter(pk__in=matched_ids)
        data = self.data
        excluded_names = data.getlist("status__exclude") if hasattr(data, 'getlist') else []
        if excluded_names:
            excl_ids = TaggedStatus.objects.filter(
                content_type=project_ct,
                tag__name__in=excluded_names,
            ).values_list("object_id", flat=True)
            queryset = queryset.exclude(pk__in=excl_ids)
        return queryset.distinct()

    def filter_search(self, queryset, name, value):
        return filter_normalized_contains(queryset, ["name", "description", "id"], value).distinct()
