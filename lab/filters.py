import django_filters
from django import forms
from django.db.models import Q
from django.contrib.contenttypes.models import ContentType
from .models import (
    Individual, Sample, Project, SampleType, TestType, Status, PipelineType,
    Institution, Test, Pipeline, Analysis, AnalysisType
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

class IndividualFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method='filter_search', label="Search")
    
    # Individual Fields
    status = TristateModelMultipleChoiceFilter(queryset=Status.objects.all(), to_field_name='name')
    sex = TristateMultipleChoiceFilter(choices=Individual._meta.get_field('sex').choices)
    is_alive = TristateMultipleChoiceFilter(choices=[(True, 'Alive'), (False, 'Deceased')])
    
    # Sample Fields
    samples__status = TristateModelMultipleChoiceFilter(
        queryset=Status.objects.all(), 
        to_field_name='name', 
        label="Sample Status"
    )
    samples__sample_type = TristateModelMultipleChoiceFilter(
        queryset=SampleType.objects.all(), 
        to_field_name='name', 
        label="Sample Type"
    )
    
    # Test Fields
    samples__tests__status = TristateModelMultipleChoiceFilter(
        queryset=Status.objects.all(),
        to_field_name='name',
        label="Test Status"
    )
    samples__tests__test_type = TristateModelMultipleChoiceFilter(
        queryset=TestType.objects.all(),
        to_field_name='name',
        label="Test Type"
    )

    # Pipeline Fields
    samples__tests__pipelines__status = TristateModelMultipleChoiceFilter(
        queryset=Status.objects.all(),
        to_field_name='name',
        label="Pipeline Status"
    )
    samples__tests__pipelines__type = TristateModelMultipleChoiceFilter(
        queryset=PipelineType.objects.all(),
        to_field_name='name',
        label="Pipeline Type"
    )
    
    # Analysis (Human Interpretation) Fields
    samples__tests__pipelines__analyses__status = TristateModelMultipleChoiceFilter(
        queryset=Status.objects.all(),
        to_field_name='name',
        label="Analysis Status"
    )
    samples__tests__pipelines__analyses__type = TristateModelMultipleChoiceFilter(
        queryset=AnalysisType.objects.all(),
        to_field_name='name',
        label="Analysis Type"
    )
    
    # Variant Fields
    # status, type, classifications
    variants__status = TristateModelMultipleChoiceFilter(
        queryset=Status.objects.all(),
        to_field_name='name',
        label="Variant Status"
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
        fields = ['status', 'sex', 'family']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically load HPO terms to avoid circular imports or excessively large lists if not needed immediately
        # But for a filter sidebar, we ideally want a manageable list or an autocomplete.
        # Given the requirements "filter individuals by everything... hpo terms", 
        # listing ALL HPO terms in a checkbox list is bad (there are thousands).
        # The user said "sidebar... toggle... click again to negate".
        # This implies a set of available options. 
        # Maybe we only show HPO terms that are actually used in the DB?
        if 'hpo_terms' in self.filters:
            # OPTIMIZATION: Do not load all used terms into choices.
            # We use a search-based UI now.
            # Django-Filter mostly uses choices for validation and widget rendering.
            # For validation, ModelMultipleChoiceFilter checks existence in queryset.
            # We must ensure the queryset covers all valid terms.
            from ontologies.models import Term
            self.filters['hpo_terms'].queryset = Term.objects.all()


        # Restrict Status choices by ContentType
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

class VariantFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method='filter_search', label="Search")

    # Core variant fields
    status = TristateModelMultipleChoiceFilter(
        queryset=Status.objects.all(),
        to_field_name='name',
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
        fields = ['status', 'zygosity']

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
    status = TristateModelMultipleChoiceFilter(queryset=Status.objects.all(), to_field_name='name')
    priority = TristateMultipleChoiceFilter(choices=[], label="Priority")  # Will be set in __init__
    created_by = TristateModelMultipleChoiceFilter(
        queryset=None,  # Will be set in __init__
        to_field_name='username',
        label="Created By"
    )
    
    class Meta:
        model = Project
        fields = ['status', 'priority']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set created_by queryset to User model
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

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) | 
            Q(description__icontains=value) |
            Q(id__icontains=value)
        ).distinct()
