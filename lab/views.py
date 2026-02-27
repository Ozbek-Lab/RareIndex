from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, DetailView
from django_tables2 import SingleTableMixin
from django_filters.views import FilterView
from django.core.cache import cache
from django.db.models import Count
from django.contrib.contenttypes.models import ContentType
from .models import (
    Individual, Sample, Task, Note, Project, Test, Pipeline, Analysis,
    Status, SampleType, TestType, PipelineType, AnalysisType, IdentifierType,
)
from .tables import IndividualTable, SampleTable, ProjectTable, VariantTable
from .filters import IndividualFilter, ProjectFilter, VariantFilter
from variant.models import Variant, Annotation as VariantAnnotation, Classification as VariantClassification


def _variant_filter_counts():
    """
    Returns per-option counts for the variant filter sidebar.

    Results are cached for 5 minutes. The counts are global (not affected by
    the current filter selection) so they only need to be refreshed when the
    underlying data changes, not on every request. The cache is invalidated
    automatically after TTL; for immediate refresh after bulk imports use
    cache.delete("variant_filter_counts").
    """
    CACHE_KEY = "variant_filter_counts"
    CACHE_TTL = 300  # seconds

    counts = cache.get(CACHE_KEY)
    if counts is not None:
        return counts

    type_counts = {
        'SNV':    Variant.objects.filter(snv__isnull=False).count(),
        'CNV':    Variant.objects.filter(cnv__isnull=False).count(),
        'SV':     Variant.objects.filter(sv__isnull=False).count(),
        'Repeat': Variant.objects.filter(repeat__isnull=False).count(),
    }

    zygosity_counts = {choice[0]: 0 for choice in Variant.ZYGOSITY_CHOICES}
    zygosity_counts.update({
        row['zygosity']: row['c']
        for row in Variant.objects.filter(zygosity__isnull=False).values('zygosity').annotate(c=Count('id'))
    })

    classif_counts = {choice[0]: 0 for choice in VariantClassification.CLASSIFICATION_CHOICES}
    classif_counts.update({
        row['classification']: row['c']
        for row in VariantClassification.objects.values('classification')
        .annotate(c=Count('variant_id', distinct=True))
        if row['classification']
    })

    variant_ct = ContentType.objects.get_for_model(Variant)
    status_counts = {s: 0 for s in Status.objects.filter(content_type=variant_ct).values_list('name', flat=True)}
    status_counts.update({
        row['status__name']: row['c']
        for row in Variant.objects.filter(status__isnull=False)
        .values('status__name')
        .annotate(c=Count('id'))
        if row['status__name']
    })
    assembly_counts = {
        row['assembly_version']: row['c']
        for row in Variant.objects.values('assembly_version').annotate(c=Count('id'))
    }
    annotation_source_counts = {
        row['source']: row['c']
        for row in VariantAnnotation.objects.values('source')
        .annotate(c=Count('variant_id', distinct=True))
    }

    counts = {
        "variant_type":      type_counts,
        "zygosity":          zygosity_counts,
        "classification":    classif_counts,
        "status":            status_counts,
        "assembly_version":  assembly_counts,
        "annotation_source": annotation_source_counts,
    }
    cache.set(CACHE_KEY, counts, CACHE_TTL)
    return counts

def _individual_filter_counts():
    """
    Returns per-option counts for the individual filter sidebar.
    Each count represents the number of distinct individuals matching that option.
    Cached for 5 minutes.
    """
    CACHE_KEY = "individual_filter_counts"
    CACHE_TTL = 300

    counts = cache.get(CACHE_KEY)
    if counts is not None:
        return counts

    individual_ct = ContentType.objects.get_for_model(Individual)
    sample_ct = ContentType.objects.get_for_model(Sample)
    test_ct = ContentType.objects.get_for_model(Test)
    pipeline_ct = ContentType.objects.get_for_model(Pipeline)
    analysis_ct = ContentType.objects.get_for_model(Analysis)
    variant_ct = ContentType.objects.get_for_model(Variant)

    # Status (keyed by status name)
    status_counts = {s: 0 for s in Status.objects.filter(content_type=individual_ct).values_list('name', flat=True)}
    status_counts.update({
        row['status__name']: row['c']
        for row in Individual.objects.values('status__name').annotate(c=Count('id'))
        if row['status__name']
    })

    # Sex (keyed by sex value: 'male', 'female', 'other')
    sex_counts = {'male': 0, 'female': 0, 'other': 0}
    sex_counts.update({
        row['sex']: row['c']
        for row in Individual.objects.filter(sex__isnull=False).values('sex').annotate(c=Count('id'))
    })

    # Is alive (keyed by Python bool True/False)
    is_alive_counts = {True: 0, False: 0}
    is_alive_counts.update({
        row['is_alive']: row['c']
        for row in Individual.objects.values('is_alive').annotate(c=Count('id'))
    })

    # Sample type (count = distinct individuals with at least one sample of this type)
    sample_type_counts = {name: 0 for name in SampleType.objects.values_list('name', flat=True)}
    sample_type_counts.update({
        row['sample_type__name']: row['c']
        for row in Sample.objects.values('sample_type__name')
        .annotate(c=Count('individual_id', distinct=True))
        if row['sample_type__name']
    })

    # Sample status
    sample_status_counts = {s: 0 for s in Status.objects.filter(content_type=sample_ct).values_list('name', flat=True)}
    sample_status_counts.update({
        row['status__name']: row['c']
        for row in Sample.objects.values('status__name')
        .annotate(c=Count('individual_id', distinct=True))
        if row['status__name']
    })

    # Test type
    test_type_counts = {name: 0 for name in TestType.objects.values_list('name', flat=True)}
    test_type_counts.update({
        row['test_type__name']: row['c']
        for row in Test.objects.filter(sample__isnull=False).values('test_type__name')
        .annotate(c=Count('sample__individual_id', distinct=True))
        if row['test_type__name']
    })

    # Test status
    test_status_counts = {s: 0 for s in Status.objects.filter(content_type=test_ct).values_list('name', flat=True)}
    test_status_counts.update({
        row['status__name']: row['c']
        for row in Test.objects.filter(sample__isnull=False).values('status__name')
        .annotate(c=Count('sample__individual_id', distinct=True))
        if row['status__name']
    })

    # Pipeline type
    pipeline_type_counts = {name: 0 for name in PipelineType.objects.values_list('name', flat=True)}
    pipeline_type_counts.update({
        row['type__name']: row['c']
        for row in Pipeline.objects.values('type__name')
        .annotate(c=Count('test__sample__individual_id', distinct=True))
        if row['type__name']
    })

    # Pipeline status
    pipeline_status_counts = {s: 0 for s in Status.objects.filter(content_type=pipeline_ct).values_list('name', flat=True)}
    pipeline_status_counts.update({
        row['status__name']: row['c']
        for row in Pipeline.objects.values('status__name')
        .annotate(c=Count('test__sample__individual_id', distinct=True))
        if row['status__name']
    })

    # Analysis type
    analysis_type_counts = {name: 0 for name in AnalysisType.objects.values_list('name', flat=True)}
    analysis_type_counts.update({
        row['type__name']: row['c']
        for row in Analysis.objects.values('type__name')
        .annotate(c=Count('pipeline__test__sample__individual_id', distinct=True))
        if row['type__name']
    })

    # Analysis status
    analysis_status_counts = {s: 0 for s in Status.objects.filter(content_type=analysis_ct).values_list('name', flat=True)}
    analysis_status_counts.update({
        row['status__name']: row['c']
        for row in Analysis.objects.values('status__name')
        .annotate(c=Count('pipeline__test__sample__individual_id', distinct=True))
        if row['status__name']
    })

    # Variant type (distinct individuals with that variant subtype)
    variant_type_counts = {
        'SNV':    Individual.objects.filter(variants__snv__isnull=False).distinct().count(),
        'CNV':    Individual.objects.filter(variants__cnv__isnull=False).distinct().count(),
        'SV':     Individual.objects.filter(variants__sv__isnull=False).distinct().count(),
        'Repeat': Individual.objects.filter(variants__repeat__isnull=False).distinct().count(),
    }

    # Variant status (distinct individuals)
    variant_status_counts = {s: 0 for s in Status.objects.filter(content_type=variant_ct).values_list('name', flat=True)}
    variant_status_counts.update({
        row['status__name']: row['c']
        for row in Variant.objects.filter(status__isnull=False).values('status__name')
        .annotate(c=Count('individual_id', distinct=True))
        if row['status__name']
    })

    # ACMG classification (distinct individuals)
    classif_counts = {choice[0]: 0 for choice in VariantClassification.CLASSIFICATION_CHOICES}
    classif_counts.update({
        row['classification']: row['c']
        for row in VariantClassification.objects.values('classification')
        .annotate(c=Count('variant__individual_id', distinct=True))
        if row['classification']
    })

    counts = {
        "status":           status_counts,
        "sex":              sex_counts,
        "is_alive":         is_alive_counts,
        "sample_type":      sample_type_counts,
        "sample_status":    sample_status_counts,
        "test_type":        test_type_counts,
        "test_status":      test_status_counts,
        "pipeline_type":    pipeline_type_counts,
        "pipeline_status":  pipeline_status_counts,
        "analysis_type":    analysis_type_counts,
        "analysis_status":  analysis_status_counts,
        "variant_type":     variant_type_counts,
        "variant_status":   variant_status_counts,
        "classification":   classif_counts,
    }
    cache.set(CACHE_KEY, counts, CACHE_TTL)
    return counts


def _project_filter_counts():
    """
    Returns per-option counts for the project filter sidebar.
    Cached for 5 minutes.
    """
    CACHE_KEY = "project_filter_counts"
    CACHE_TTL = 300

    counts = cache.get(CACHE_KEY)
    if counts is not None:
        return counts

    project_ct = ContentType.objects.get_for_model(Project)

    # Status (keyed by status name)
    status_counts = {s: 0 for s in Status.objects.filter(content_type=project_ct).values_list('name', flat=True)}
    status_counts.update({
        row['status__name']: row['c']
        for row in Project.objects.values('status__name').annotate(c=Count('id'))
        if row['status__name']
    })

    # Priority (keyed by priority value: 'low', 'medium', 'high', 'urgent')
    priority_counts = {choice[0]: 0 for choice in Task.PRIORITY_CHOICES}
    priority_counts.update({
        row['priority']: row['c']
        for row in Project.objects.values('priority').annotate(c=Count('id'))
        if row['priority']
    })

    # Created by (keyed by username; no zero-seeding since it's dynamic)
    created_by_counts = {
        row['created_by__username']: row['c']
        for row in Project.objects.values('created_by__username').annotate(c=Count('id'))
        if row['created_by__username']
    }

    counts = {
        "status":     status_counts,
        "priority":   priority_counts,
        "created_by": created_by_counts,
    }
    cache.set(CACHE_KEY, counts, CACHE_TTL)
    return counts


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "lab/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['now'] = timezone.now()
        
        tasks = Task.objects.filter(assigned_to=self.request.user)
        context['my_tasks'] = tasks.exclude(
            status__name__iexact="completed"
        ).order_by('due_date', '-priority')[:10]
        
        context['completed_tasks'] = tasks.filter(
            status__name__iexact="completed"
        ).order_by('-id')[:5]

        # 1.5 Header Stats
        context['individual_count'] = Individual.objects.count()
        context['sample_count'] = Sample.objects.count()
        
        # 2. News Feed - Aggregated History
        from itertools import chain
        from operator import attrgetter
        
        # Helper to get recent history
        def get_history(model):
            return model.history.all().order_by('-history_date')[:10]
        
        # Helper to get field diff
        def get_field_diff(new_hist, old_hist):
            if not old_hist:
                return {}
            changes = {}
            ignore_fields = {"history_id", "history_date", "history_type", "history_user", "history_change_reason"}
            for field in new_hist._meta.fields:
                name = field.name
                if name in ignore_fields:
                    continue
                # Use raw FK id (e.g. family_id) to avoid DoesNotExist when related object was deleted
                if getattr(field, "remote_field", None) and getattr(field, "attname", None):
                    new_val = getattr(new_hist, field.attname, None)
                    old_val = getattr(old_hist, field.attname, None)
                else:
                    new_val = getattr(new_hist, name, None)
                    old_val = getattr(old_hist, name, None)
                if new_val != old_val:
                    # Simple string representation for now
                    changes[name] = f"'{old_val}' → '{new_val}'"
            return changes

        individual_history = get_history(Individual)
        sample_history = get_history(Sample)
        note_history = get_history(Note)
        project_history = get_history(Project)
        test_history = get_history(Test)
        pipeline_history = get_history(Pipeline)
        
        # Combine and sort
        combined_history = sorted(
            chain(individual_history, sample_history, note_history, project_history, test_history, pipeline_history),
            key=attrgetter('history_date'),
            reverse=True
        )
        
        feed_items = combined_history[:20]
        
        # Model name from history class (e.g. HistoricalTest -> Test) so template never touches instance FKs
        def _history_model_name(hist_record):
            name = type(hist_record).__name__
            return name.replace("Historical", "", 1) if name.startswith("Historical") else name

        # Calculate diffs and safe display for each item (avoid DoesNotExist when related objects were deleted)
        for item in feed_items:
            item.safe_model_name = _history_model_name(item)
            try:
                item.safe_instance_repr = str(item.instance)
            except Exception:
                pk = getattr(item, "id", "?")
                item.safe_instance_repr = f"{item.safe_model_name} #{pk}"
            try:
                item.safe_instance_url = getattr(item.instance, "get_absolute_url", None) and item.instance.get_absolute_url()
            except Exception:
                item.safe_instance_url = None
            if item.history_type == '~':  # Update
                prev = item.prev_record
                if prev:
                    item.diff_display = get_field_diff(item, prev)
        
        context['news_feed'] = feed_items
        
        return context

class IndividualListView(LoginRequiredMixin, SingleTableMixin, FilterView):
    model = Individual
    table_class = IndividualTable
    filterset_class = IndividualFilter
    template_name = "lab/individual_list.html"
    paginate_by = 25
    
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_count'] = self.model.objects.count()
        # Status Metadata for colored pills
        from .models import Status
        statuses = Status.objects.all()
        metadata = {}
        for s in statuses:
            metadata[s.name] = {
                'color': s.color,
                'icon': s.icon,
                'short_name': s.short_name,
            }
        context['status_metadata'] = metadata
        
        # Filter counts are only needed on full page render (sidebar is present)
        if not self.request.htmx:
            context['filter_counts'] = _individual_filter_counts()
        else:
            context['filter_counts'] = {}

        # Get filtered queryset to calculate distinct families
        if 'filter' in context:
            qs = context['filter'].qs
        else:
            qs = self.get_queryset()
        
        # Count distinct non-null families the filtered individuals belong to
        context['family_count'] = qs.exclude(family__isnull=True).values('family').distinct().count()
        context['affected_count'] = qs.filter(is_affected=True).count()
        context['index_count'] = qs.filter(is_index=True).count()

        # Load Selected HPO Terms
        hpo_term_ids = self.request.GET.getlist('hpo_terms')
        if hpo_term_ids:
            from ontologies.models import Term
            # Handle potential non-integer inputs (though typical use is IDs)
            # Filter handles OBO IDs, but for "selected list" display we want DB objects.
            # Convert string IDs to integers where possible for PK lookup
            clean_ids = []
            for tid in hpo_term_ids:
                try:
                    clean_ids.append(int(tid))
                except ValueError:
                    continue # Skip OBO strings for the display list for now, or handle lookup
            
            context['selected_hpo_terms'] = Term.objects.filter(pk__in=clean_ids)
            
        return context
    
    def get_template_names(self):
        if self.request.htmx:
            # Filtering / Sorting / Global Search (Targeting the table container)
            # This MUST come before infinite scroll check because sorting/filtering
            # might include a 'page' parameter in the URL.
            if self.request.headers.get('HX-Target') == 'individual-table-container':
                return ["lab/partials/individual_table.html"]
            
            # Infinite Scroll (returns only new rows to append)
            if self.request.GET.get("page"):
                return ["lab/partials/individual_rows.html"]
            
            # Reset All / Full Navigation (return full page to swap body)
            return ["lab/individual_list.html"]
            
        return ["lab/individual_list.html"]

class ProjectListView(LoginRequiredMixin, SingleTableMixin, FilterView):
    model = Project
    table_class = ProjectTable
    filterset_class = ProjectFilter
    template_name = "lab/project_list.html"
    paginate_by = 25
    
    def get_queryset(self):
        # Optimize query by prefetching individuals and their families
        return super().get_queryset().prefetch_related(
            'individuals',
            'individuals__family',
            'status',
            'created_by'
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_count'] = self.model.objects.count()
        # Status Metadata for colored pills
        from .models import Status
        statuses = Status.objects.all()
        metadata = {}
        for s in statuses:
            metadata[s.name] = {
                'color': s.color,
                'icon': s.icon,
                'short_name': s.short_name,
            }
        context['status_metadata'] = metadata

        # Filter counts are only needed on full page render (sidebar is present)
        if not self.request.htmx:
            context['filter_counts'] = _project_filter_counts()
        else:
            context['filter_counts'] = {}
        
        return context
    
    def get_template_names(self):
        if self.request.htmx:
            # Filtering / Sorting / Global Search (Targeting the table container)
            if self.request.headers.get('HX-Target') == 'project-table-container':
                return ["lab/partials/project_table.html"]
            
            # Infinite Scroll (returns only new rows to append)
            if self.request.GET.get("page"):
                return ["lab/partials/project_rows.html"]
            
            # Reset All / Full Navigation (return full page to swap body)
            return ["lab/project_list.html"]
            
        return ["lab/project_list.html"]


class VariantListView(LoginRequiredMixin, SingleTableMixin, FilterView):
    model = Variant
    table_class = VariantTable
    filterset_class = VariantFilter
    template_name = "lab/variant_list.html"
    paginate_by = 25

    def get_queryset(self):
        return super().get_queryset().select_related("individual", "status").prefetch_related("genes")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_count"] = self.model.objects.count()

        statuses = Status.objects.all()
        metadata = {}
        for s in statuses:
            metadata[s.name] = {
                "color": s.color,
                "icon": s.icon,
                "short_name": s.short_name,
            }
        context["status_metadata"] = metadata

        # Filter counts are only needed when the full page renders (sidebar included).
        # HTMX filter/search/scroll requests only swap the table container, so skip
        # the count queries entirely on those — they would be computed but never used.
        if not self.request.htmx:
            context["filter_counts"] = _variant_filter_counts()
        else:
            context["filter_counts"] = {}

        return context

    def get_template_names(self):
        if self.request.htmx:
            if self.request.headers.get('HX-Target') == 'variant-table-container':
                return ["lab/partials/variant_table.html"]
            if self.request.GET.get("page"):
                return ["lab/partials/variant_rows.html"]
            return ["lab/variant_list.html"]
        return ["lab/variant_list.html"]

from django.views.generic import ListView, DetailView
from django.db.models import Q
from ontologies.models import Term

class HPOTermSearchView(LoginRequiredMixin, ListView):
    model = Term
    context_object_name = "results"
    paginate_by = 20
    
    def get_template_names(self):
        if self.template_name:
            return [self.template_name]
        if self.request.GET.get('variant') == 'picker':
            return ["lab/partials/hpo_search_results_picker.html"]
        if self.request.GET.get('variant') == 'picker_client':
            return ["lab/partials/hpo_picker_results_client.html"]
        return ["lab/partials/hpo_search_results.html"]
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        individual_id = self.request.GET.get('individual_id')
        if individual_id:
            context['individual'] = get_object_or_404(Individual, pk=individual_id)
        return context
    
    def get_queryset(self):
        query = self.request.GET.get('q')
        if not query:
            return Term.objects.none()
            
        # Base filter
        qs = Term.objects.filter(
            Q(label__icontains=query) | Q(identifier__icontains=query)
        ).filter(ontology__type=1) # HPO Only
        
        # Exclude already selected terms
        individual_id = self.request.GET.get('individual_id')
        if individual_id:
            try:
                individual = Individual.objects.get(pk=individual_id)
                qs = qs.exclude(pk__in=individual.hpo_terms.all())
            except Individual.DoesNotExist:
                pass

        # Annotate for ordering relevance
        from django.db.models import Case, When, Value, IntegerField
        from django.db.models.functions import Length
        
        qs = qs.annotate(
            is_exact=Case(
                When(label__iexact=query, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            starts_with=Case(
                When(label__istartswith=query, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            label_len=Length('label')
        ).order_by('is_exact', 'starts_with', 'label_len', 'label')
        
        return qs


class RenderSelectedHPOTermView(LoginRequiredMixin, DetailView):
    model = Term
    template_name = "lab/partials/hpo_selected_term.html"
    context_object_name = "term"

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        # Trigger filter change on client side
        response["HX-Trigger"] = "filter-changed"
        return response


class SampleListView(LoginRequiredMixin, SingleTableMixin, FilterView):
    model = Sample
    table_class = SampleTable
    template_name = "lab/sample_list.html"
    paginate_by = 25

    def get_template_names(self):
        if self.request.htmx:
            return ["lab/partials/sample_table.html"]

class ProjectDetailView(LoginRequiredMixin, DetailView):
    model = Project
    template_name = "lab/project_detail.html"
    context_object_name = "project"

    def get_queryset(self):
        return Project.objects.prefetch_related(
            'individuals',
            'individuals__cross_ids__id_type',
            'individuals__status',
            'individuals__institution',
            'status',
            'created_by',
        )


class IndividualDetailView(LoginRequiredMixin, DetailView):
    model = Individual
    template_name = "lab/individual_detail.html"
    context_object_name = "individual"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Prefetch related data for performance
        individual = Individual.objects.prefetch_related(
            'samples', 
            'samples__tests',
            'samples__tests__pipelines',
            'cross_ids',
            'cross_ids__id_type',
            'hpo_terms',
            'institution',
            'physicians',
            'projects',
            'family__individuals',
            'family__individuals__cross_ids__id_type',
            'family__individuals__status',
        ).get(pk=self.kwargs['pk'])
        
        context['individual'] = individual

        primary_type = IdentifierType.objects.filter(use_priority=1).order_by("id").first()
        secondary_type = IdentifierType.objects.filter(use_priority=2).order_by("id").first()
        context['primary_id_type_name'] = primary_type.name if primary_type else "Primary ID"
        context['secondary_id_type_name'] = secondary_type.name if secondary_type else "Secondary ID"

        primary_xid = individual.cross_ids.filter(id_type__use_priority=1).order_by("id_type__id").first()
        context['display_id'] = primary_xid.id_value if primary_xid else individual.pk
        
        # Explicitly pass history to context with field diffs
        history_qs = individual.history.all().select_related('history_user')[:20]
        history_list = list(history_qs)
        
        # Add diff information for updates
        for i, record in enumerate(history_list):
            if record.history_type == '~':  # Update
                # Get the previous record
                prev = history_list[i + 1] if i + 1 < len(history_list) else None
                if prev:
                    record.diff_display = self._get_field_diff(record, prev)
                else:
                    record.diff_display = {}
            else:
                record.diff_display = {}
        
        context['history_records'] = history_list
        return context
    
    def _get_field_diff(self, new_hist, old_hist):
        """Calculate field-level differences between two history records."""
        if not old_hist:
            return {}
        changes = {}
        ignore_fields = {"history_id", "history_date", "history_type", "history_user", "history_change_reason", "id"}
        for field in new_hist._meta.fields:
            name = field.name
            if name in ignore_fields:
                continue
            new_val = getattr(new_hist, name, None)
            old_val = getattr(old_hist, name, None)
            if new_val != old_val:
                # Format field name nicely
                field_label = name.replace('_', ' ').title()
                # Handle None values
                old_display = old_val if old_val is not None else "(empty)"
                new_display = new_val if new_val is not None else "(empty)"
                changes[field_label] = f"'{old_display}' → '{new_display}'"
        return changes

    def render_to_response(self, context, **response_kwargs):
        if self.request.htmx and "partial" in self.request.GET:
            partial_name = self.request.GET.get("partial")
            if partial_name == "detail":
                return render(self.request, "lab/partials/individual_detail.html", context)
            elif partial_name == "history":
                return render(self.request, "lab/partials/tabs/_history.html", context)
            elif partial_name == "workflow":
                return render(self.request, "lab/partials/tabs/_workflow.html", context)
            elif partial_name in ["phenotype", "hpo_card"]:
                # Phenotype tab is in _phenotype.html
                target = f"lab/partials/tabs/_phenotype.html#{partial_name}" if partial_name != "phenotype" else "lab/partials/tabs/_phenotype.html"
                return render(self.request, target, context)
            
            # Default fallback or error
            return render(self.request, f"lab/partials/tabs/_phenotype.html#{partial_name}", context)
        return super().render_to_response(context, **response_kwargs)


from django.views.generic import CreateView
from django.shortcuts import redirect
from django.forms import formset_factory
from .forms import CreateFamilyForm, FamilyMemberForm
from .models import Family, Note, CrossIdentifier, IdentifierType
import json

class FamilyCreateView(LoginRequiredMixin, CreateView):
    model = Family
    form_class = CreateFamilyForm
    template_name = "lab/family_create.html"
    success_url = "/individuals/" # TODO: Redirect to family detail

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        IndividualFormSet = formset_factory(FamilyMemberForm, extra=0)
        
        # Pass identifier types to context for the frontend
        context['identifier_types'] = IdentifierType.objects.all()
        
        # Pass institutions for client-side search
        from .models import Institution
        context['institutions_list'] = list(Institution.objects.values('id', 'name'))
        
        if self.request.POST:
            context['individual_formset'] = IndividualFormSet(self.request.POST, prefix='individuals')
        else:
            context['individual_formset'] = IndividualFormSet(prefix='individuals')
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        individual_formset = context['individual_formset']
        
        if individual_formset.is_valid():
            self.object = form.save(commit=False)
            self.object.created_by = self.request.user
            self.object.save()
            
            saved_individuals = {} # Map form index -> saved instance
            
            # Pass 1: Save all individuals and their non-relational data
            for i, inline_form in enumerate(individual_formset):
                if inline_form.cleaned_data and not inline_form.cleaned_data.get('DELETE', False):
                    individual = inline_form.save(commit=False)
                    individual.family = self.object
                    individual.created_by = self.request.user
                    
                    # Ensure status is set if missing (though form requires it usually)
                    if not individual.status_id:
                        from .models import Status
                        status = Status.objects.first()
                        if status:
                            individual.status = status
                    
                    individual.save()
                    individual.institution.set(inline_form.cleaned_data['institution'])
                    individual.hpo_terms.set(inline_form.cleaned_data['hpo_terms'])
                    
                    saved_individuals[i] = individual
                    
                    # Handle Note
                    note_content = inline_form.cleaned_data.get('note_content')
                    if note_content:
                        Note.objects.create(
                            content=note_content,
                            user=self.request.user,
                            content_object=individual
                        )
                        
                    # Handle Cross Identifiers
                    cross_ids_json = inline_form.cleaned_data.get('cross_identifiers_json')
                    if cross_ids_json:
                        try:
                            cross_ids_data = json.loads(cross_ids_json)
                            for item in cross_ids_data:
                                type_id = item.get('type_id')
                                value = item.get('value')
                                if type_id and value:
                                    CrossIdentifier.objects.create(
                                        individual=individual,
                                        id_type_id=type_id,
                                        id_value=value,
                                        created_by=self.request.user
                                    )
                        except json.JSONDecodeError:
                            pass # TODO: Log error?

            # Pass 2: Resolve relationships (Mother/Father)
            for i, inline_form in enumerate(individual_formset):
                 if i in saved_individuals:
                    individual = saved_individuals[i]
                    father_ref = inline_form.cleaned_data.get('father_ref')
                    mother_ref = inline_form.cleaned_data.get('mother_ref')
                    
                    updated = False
                    if father_ref is not None and father_ref != "":
                        try:
                            ref_idx = int(father_ref)
                            if ref_idx in saved_individuals:
                                individual.father = saved_individuals[ref_idx]
                                updated = True
                        except ValueError:
                            pass
                            
                    if mother_ref is not None and mother_ref != "":
                        try:
                            ref_idx = int(mother_ref)
                            if ref_idx in saved_individuals:
                                individual.mother = saved_individuals[ref_idx]
                                updated = True
                        except ValueError:
                            pass
                    
                    if updated:
                        individual.save(update_fields=['father', 'mother'])

            return redirect(self.success_url)
        else:
            return self.render_to_response(self.get_context_data(form=form))

class CompleteTaskView(LoginRequiredMixin, TemplateView):
    def post(self, request, pk):
        from .models import Task
        task = get_object_or_404(Task, pk=pk)
        
        # Only allow assigned user or creator to complete?
        # For now, let's say assigned user or superuser
        if task.assigned_to != request.user and not request.user.is_superuser:
            return HttpResponseForbidden("You are not assigned to this task.")
            
        task.complete(request.user)
        
        response = HttpResponse("")
        response["HX-Trigger"] = "taskChanged"
        return response


class ReopenTaskView(LoginRequiredMixin, TemplateView):
    def post(self, request, pk):
        from .models import Task
        task = get_object_or_404(Task, pk=pk)

        # Permission check
        if task.assigned_to != request.user and not request.user.is_superuser:
            return HttpResponseForbidden("You cannot reopen this task.")

        # Reopen logic
        if task.status.name.lower() == "completed":
            if task.previous_status:
                task.status = task.previous_status
                task.previous_status = None
            else:
                # Fallback if no previous status (e.g. historical data)
                # Try to find a 'pending' or 'in progress' status
                pending_status = Status.objects.filter(name__iexact="pending").first() or \
                                 Status.objects.all().first()
                task.status = pending_status
            
            task.save()
            
            # If we want to refresh both the active list and finished list, 
            # we need to return something that triggers a refresh or use OOB.
            # For now, let's refresh the whole tasks partial.
            # But the view logic for DashboardView is a TemplateView.
            # We might want a dedicated partial view or just return a trigger.
            
            response = HttpResponse("")
            response["HX-Trigger"] = "taskChanged"
            return response

        return HttpResponse("")

import csv
from django.views import View

class IndividualExportView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        # 1. Apply Filters (Same as List View)
        qs = Individual.objects.all().prefetch_related(
            'samples', 'samples__tests', 'cross_ids', 'hpo_terms',
            'institution', 'physicians', 'projects', 'family',
             'samples__isolation_by', 'samples__tests__test_type'
        )
        filter = IndividualFilter(request.GET, queryset=qs)
        filtered_qs = filter.qs.distinct()

        # 2. Prepare Response
        response = HttpResponse(content_type='text/csv')
        filename = f"individuals_export_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        
        # 3. Write Header
        header = [
            # IDs
            "Primary ID", "Secondary ID", "Ad-Soyad", "TC Kimlik No", "Other IDs",
            # Demographics
            "Doğum Tarihi", "Cinsiyet", "Durum", # Status
            # Clinical
            "ICD11", "HPO kodları", "Tanı", "Geliş Tarihi", "Kurum Notları", 
            
            # Relations
            "Gönderen Kurum/Birim", "Klinisyen & İletişim Bilgileri", "Konsey Tarihi", "Takip Notları", "Genel Notlar/Sonuçlar",
            
            # Sample & Test (Flattened)
            "Örnek Tipi", "Örnek Notları", "İzolasyonu yapan", "Örnek gön.& OD değ.", # Sample Measurements
            "Çalışılan Test Adı", "Test Notları", "Çalışılma Tarihi", "Hiz.Alım.Gön. Tarihi", "Data Geliş tarihi",
            
            # Projects
            "Projeler"
        ]
        # BOM for Excel compatibility with UTF-8
        response.write(u'\ufeff'.encode('utf8'))
        writer.writerow(header)

        # 4. Write Rows — ONE row per individual, aggregated sample/test data
        for individual in filtered_qs:
            # Base Individual Data
            primary_id = individual.primary_id
            secondary_id = individual.secondary_id
            
            # Other IDs
            other_ids_list = [
                f"{x.id_type.name}:{x.id_value}" 
                for x in individual.cross_ids.all() 
                if x.id_type.use_priority not in [1, 2]
            ]
            other_ids = "; ".join(other_ids_list)
            
            name = individual.full_name
            
            if not request.user.has_perm("lab.view_sensitive_data"):
                name = "*****"
                tc = "*****"
            else:
                tc = str(individual.tc_identity) if individual.tc_identity else ""
            
            dob = individual.birth_date
            sex = individual.get_sex_display() if individual.sex else ""
            status = individual.status.name if individual.status else ""
            
            icd11 = individual.icd11_code or ""
            hpo = "; ".join([t.identifier for t in individual.hpo_terms.all()])
            diagnosis = individual.diagnosis or ""
            council_date = individual.council_date or ""
            
            # Notes
            general_notes = " | ".join([n.content for n in individual.notes.all()])
            
            institution_names = "; ".join([i.name for i in individual.institution.all()])
            physicians = "; ".join([u.get_full_name() or u.username for u in individual.physicians.all()])
            projects = "; ".join([p.name for p in individual.projects.all()])

            # Aggregate Sample data
            samples = individual.samples.all()
            receipt_dates = []
            sample_types = []
            sample_notes_list = []
            isolation_by_list = []
            measurements_list = []
            
            # Aggregate Test data
            test_names = []
            test_notes_list = []
            test_dates = []
            service_dates = []
            data_dates = []
            
            for sample in samples:
                if sample.receipt_date:
                    receipt_dates.append(str(sample.receipt_date))
                if sample.sample_type:
                    sample_types.append(sample.sample_type.name)
                s_notes = " | ".join([n.content for n in sample.notes.all()])
                if s_notes:
                    sample_notes_list.append(s_notes)
                if sample.isolation_by:
                    iso_name = sample.isolation_by.get_full_name() or sample.isolation_by.username
                    isolation_by_list.append(iso_name)
                if sample.sample_measurements:
                    measurements_list.append(sample.sample_measurements)
                    
                for test in sample.tests.all():
                    if test.test_type:
                        test_names.append(test.test_type.name)
                    t_notes = " | ".join([n.content for n in test.notes.all()])
                    if t_notes:
                        test_notes_list.append(t_notes)
                    if test.performed_date:
                        test_dates.append(str(test.performed_date))
                    if test.service_send_date:
                        service_dates.append(str(test.service_send_date))
                    if test.data_receipt_date:
                        data_dates.append(str(test.data_receipt_date))

            row = [
                primary_id, secondary_id, name, tc, other_ids,
                dob, sex, status,
                icd11, hpo, diagnosis,
                "; ".join(receipt_dates) if receipt_dates else (individual.created_at.date() if individual.created_at else ""),
                "",  # Kurum Notları
                institution_names, physicians, council_date, "",  # Takip Notları
                general_notes,
                "; ".join(sample_types), "; ".join(sample_notes_list),
                "; ".join(isolation_by_list), "; ".join(measurements_list),
                "; ".join(test_names), "; ".join(test_notes_list),
                "; ".join(test_dates), "; ".join(service_dates), "; ".join(data_dates),
                projects
            ]
            writer.writerow(row)

        return response


@login_required
def configurations_view(request):
    """
    Configuration catalogue page.  Shows one collapsible section per config
    model; a section is visible only when the user has view or change permission
    on that model.
    """
    from .htmx_views import _get_config_registry, _build_section_context

    registry = _get_config_registry()

    CONFIG_PERMISSIONS = [
        f"lab.change_{key}" for key in registry
    ] + [f"lab.view_{key}" for key in registry]

    has_any = any(request.user.has_perm(p) for p in CONFIG_PERMISSIONS)
    if not has_any:
        return HttpResponseForbidden("You do not have permission to view Configurations.")

    sections = []
    for key, config in registry.items():
        can_view = request.user.has_perm(f"lab.view_{key}")
        can_change = request.user.has_perm(f"lab.change_{key}")
        if can_view or can_change:
            # Wrap each section in a dict with key "section" so the
            # config_section.html partial can use {{ section.xxx }} in both
            # the include context and the direct render context.
            sections.append(_build_section_context(request, key, config))

    return render(request, "lab/configurations.html", {"sections": sections})
