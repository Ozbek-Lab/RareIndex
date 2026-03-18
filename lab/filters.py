import django_filters
from django import forms
from django.db.models import Q
from django.contrib.contenttypes.models import ContentType
from .models import (
    Individual, Sample, Project, SampleType, TestType, Status, PipelineType,
    Institution, Test, Pipeline, Analysis, AnalysisType, TaggedStatus,
)
from variant.models import Classification, Variant, Annotation

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
             # Standard "OR" logic for multiple choices in the same field.
             # ModelMultipleChoiceFilter converts input strings to model instances in 'value'.
             # MultipleChoiceFilter keeps strings in 'value'.
             # In both cases, we want to filter by the field using 'in' lookup.
            lookup = f"{self.field_name}__in"
            queryset = queryset.filter(**{lookup: value})

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
    ct = ContentType.objects.get_for_model(model_class)
    matched_ids = TaggedStatus.objects.filter(
        content_type=ct,
        tag__in=status_values,
    ).values_list("object_id", flat=True)
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

    variants__classifications__classification = TristateMultipleChoiceFilter(
        choices=Classification.CLASSIFICATION_CHOICES,
        label="ACMG Classification"
    )

    has_report = django_filters.ChoiceFilter(
        choices=[('true', 'Yes'), ('false', 'No')],
        method='filter_has_report',
        label="Has Report",
        empty_label=None,
    )
    has_request_form = django_filters.ChoiceFilter(
        choices=[('true', 'Yes'), ('false', 'No')],
        method='filter_has_request_form',
        label="Has Request Form",
        empty_label=None,
    )
    projects = django_filters.MultipleChoiceFilter(
        field_name='projects__name',
        choices=[],
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
            selected_db_ids = set()
            selected_obo_ids = set()
            
            for v in value:
                try:
                    selected_db_ids.add(int(v))
                except (ValueError, TypeError):
                    selected_obo_ids.add(str(v))
                    
            relevant_term_ids = set()
            if selected_db_ids:
                relevant_term_ids.update(get_descendants(selected_db_ids))
            if selected_obo_ids:
                relevant_term_ids.update(get_descendants_from_obo(selected_obo_ids))
            
            queryset = queryset.filter(hpo_terms__in=relevant_term_ids)

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
            queryset = queryset.filter(institution__name__icontains=value)
        return queryset.distinct()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'hpo_terms' in self.filters:
            from ontologies.models import Term
            self.filters['hpo_terms'].queryset = Term.objects.all()

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

    def _restrict_status_queryset(self, field_name, model_class):
        if field_name in self.filters:
            ct = ContentType.objects.get_for_model(model_class)
            self.filters[field_name].queryset = Status.objects.filter(content_type=ct)

    # --- Custom method filters for status fields (TaggedStatus/GenericFK based) ---

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
        if value:
            queryset = _filter_by_tagged_status(queryset, Individual, value)
        excluded = self._get_exclude_statuses('status', Individual)
        if excluded.exists():
            queryset = _filter_by_tagged_status(queryset, Individual, excluded, exclude=True)
        return queryset.distinct()

    def filter_sample_status(self, queryset, name, value):
        sample_ct = ContentType.objects.get_for_model(Sample)
        if value:
            sample_ids = TaggedStatus.objects.filter(content_type=sample_ct, tag__in=value).values_list("object_id", flat=True)
            queryset = queryset.filter(samples__id__in=sample_ids)
        excluded = self._get_exclude_statuses('samples__status', Sample)
        if excluded.exists():
            excl_sample_ids = TaggedStatus.objects.filter(content_type=sample_ct, tag__in=excluded).values_list("object_id", flat=True)
            queryset = queryset.exclude(samples__id__in=excl_sample_ids)
        return queryset.distinct()

    def filter_test_status(self, queryset, name, value):
        test_ct = ContentType.objects.get_for_model(Test)
        if value:
            test_ids = TaggedStatus.objects.filter(content_type=test_ct, tag__in=value).values_list("object_id", flat=True)
            queryset = queryset.filter(samples__tests__id__in=test_ids)
        excluded = self._get_exclude_statuses('samples__tests__status', Test)
        if excluded.exists():
            excl_ids = TaggedStatus.objects.filter(content_type=test_ct, tag__in=excluded).values_list("object_id", flat=True)
            queryset = queryset.exclude(samples__tests__id__in=excl_ids)
        return queryset.distinct()

    def filter_pipeline_status(self, queryset, name, value):
        pipeline_ct = ContentType.objects.get_for_model(Pipeline)
        if value:
            pipe_ids = TaggedStatus.objects.filter(content_type=pipeline_ct, tag__in=value).values_list("object_id", flat=True)
            queryset = queryset.filter(samples__tests__pipelines__id__in=pipe_ids)
        excluded = self._get_exclude_statuses('samples__tests__pipelines__status', Pipeline)
        if excluded.exists():
            excl_ids = TaggedStatus.objects.filter(content_type=pipeline_ct, tag__in=excluded).values_list("object_id", flat=True)
            queryset = queryset.exclude(samples__tests__pipelines__id__in=excl_ids)
        return queryset.distinct()

    def filter_analysis_status(self, queryset, name, value):
        analysis_ct = ContentType.objects.get_for_model(Analysis)
        if value:
            analysis_ids = TaggedStatus.objects.filter(content_type=analysis_ct, tag__in=value).values_list("object_id", flat=True)
            queryset = queryset.filter(samples__tests__pipelines__analyses__id__in=analysis_ids)
        excluded = self._get_exclude_statuses('samples__tests__pipelines__analyses__status', Analysis)
        if excluded.exists():
            excl_ids = TaggedStatus.objects.filter(content_type=analysis_ct, tag__in=excluded).values_list("object_id", flat=True)
            queryset = queryset.exclude(samples__tests__pipelines__analyses__id__in=excl_ids)
        return queryset.distinct()

    def filter_variant_status(self, queryset, name, value):
        variant_ct = ContentType.objects.get_for_model(Variant)
        if value:
            variant_ids = TaggedStatus.objects.filter(content_type=variant_ct, tag__in=value).values_list("object_id", flat=True)
            queryset = queryset.filter(variants__id__in=variant_ids)
        excluded = self._get_exclude_statuses('variants__status', Variant)
        if excluded.exists():
            excl_ids = TaggedStatus.objects.filter(content_type=variant_ct, tag__in=excluded).values_list("object_id", flat=True)
            queryset = queryset.exclude(variants__id__in=excl_ids)
        return queryset.distinct()

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(full_name__icontains=value) | 
            Q(cross_ids__id_value__icontains=value) |
            Q(id__icontains=value)
        ).distinct()

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
        excluded_values = data.getlist(f"{name}__exclude")
        
        exclude_q = Q()
        if 'SNV' in excluded_values:
            exclude_q |= Q(variants__snv__isnull=False)
        if 'CNV' in excluded_values:
            exclude_q |= Q(variants__cnv__isnull=False)
        if 'SV' in excluded_values:
            exclude_q |= Q(variants__sv__isnull=False)
        if 'Repeat' in excluded_values:
            exclude_q |= Q(variants__repeat__isnull=False)
            
        if value:
            queryset = queryset.filter(q_obj)
        if excluded_values:
            queryset = queryset.exclude(exclude_q)
            
        return queryset.distinct()

    def filter_has_report(self, queryset, name, value):
        if value == 'true':
            return queryset.filter(samples__tests__pipelines__analyses__reports__isnull=False).distinct()
        elif value == 'false':
            return queryset.filter(samples__tests__pipelines__analyses__reports__isnull=True).distinct()
        return queryset

    def filter_has_request_form(self, queryset, name, value):
        if value == 'true':
            return queryset.filter(analysis_request_forms__isnull=False).distinct()
        elif value == 'false':
            return queryset.filter(analysis_request_forms__isnull=True).distinct()
        return queryset

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
    classifications__classification = TristateMultipleChoiceFilter(
        choices=Classification.CLASSIFICATION_CHOICES,
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
    gnomad_af_max = django_filters.NumberFilter(
        method='filter_gnomad_af_max',
        label="gnomAD AF ≤",
    )

    class Meta:
        model = Variant
        fields = ['zygosity']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Restrict Status choices to Variant content type
        ct = ContentType.objects.get_for_model(Variant)
        self.filters['status'].queryset = Status.objects.filter(content_type=ct)

        # Dynamically build assembly choices from existing data
        assemblies = (
            Variant.objects.values_list('assembly_version', flat=True)
            .distinct()
            .order_by('assembly_version')
        )
        self.filters['assembly_version'].field.choices = [(a, a) for a in assemblies if a]

        # Dynamically build annotation source choices
        sources = (
            Annotation.objects.values_list('source', flat=True)
            .distinct()
            .order_by('source')
        )
        self.filters['annotation_source'].field.choices = [(s, s) for s in sources if s]

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
        return queryset.filter(
            Q(chromosome__icontains=value)
            | Q(individual__primary_id__icontains=value)
            | Q(genes__symbol__icontains=value)
        ).distinct()

    def filter_gene(self, queryset, name, value):
        return queryset.filter(genes__symbol__icontains=value).distinct()

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
        return queryset.filter(
            Q(name__icontains=value) |
            Q(description__icontains=value) |
            Q(id__icontains=value)
        ).distinct()
