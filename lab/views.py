import logging
from django.conf import settings
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, DetailView
from django_tables2 import SingleTableMixin
from django_filters.views import FilterView
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, Min, Max, Sum, Avg, DateTimeField
from django.db.models.functions import Cast, Coalesce
from django.contrib.contenttypes.models import ContentType
from .models import (
    Individual,
    Sample,
    Task,
    Note,
    Project,
    Test,
    Pipeline,
    Analysis,
    Status,
    SampleType,
    TestType,
    PipelineType,
    AnalysisType,
    IdentifierType,
    Institution,
    PlotTemplate,
    DashboardWidget,
)
from .tables import IndividualTable, SampleTable, ProjectTable, VariantTable
from .filters import IndividualFilter, ProjectFilter, VariantFilter
from variant.models import Variant, Annotation as VariantAnnotation, Classification as VariantClassification

logger = logging.getLogger(__name__)


def _plot_config_filters(config):
    return config.get("filters") or config.get("filter") or {}


def _plot_build_annotations(annotate_spec):
    """Map query_config.annotate to Django ORM annotations (incl. count shorthand)."""
    if not annotate_spec:
        return {}
    annotations = {}
    for alias, agg_spec in annotate_spec.items():
        if isinstance(agg_spec, str):
            annotations[alias] = Count(agg_spec)
        elif isinstance(agg_spec, dict):
            for agg_type, field in agg_spec.items():
                agg_type_l = str(agg_type).lower()
                if agg_type_l == "count":
                    annotations[alias] = Count(field)
                elif agg_type_l == "sum":
                    annotations[alias] = Sum(field)
                elif agg_type_l == "avg":
                    annotations[alias] = Avg(field)
                elif agg_type_l == "min":
                    annotations[alias] = Min(field)
                elif agg_type_l == "max":
                    annotations[alias] = Max(field)
                else:
                    raise ValueError(f"Unknown aggregation type: {agg_type!r}")
        else:
            raise ValueError(
                f"annotate entry {alias!r} must be a field name (str) or an aggregation dict"
            )
    return annotations


def _plot_ensure_dict_rows(qs):
    """Force Values-style rows so JsonResponse always receives list[dict]."""
    if qs.query.values_select:
        return qs
    return qs.values()


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

    from .models import TaggedStatus
    variant_ct = ContentType.objects.get_for_model(Variant)
    status_counts = {s: 0 for s in Status.objects.filter(content_type=variant_ct).values_list('name', flat=True)}
    status_counts.update({
        row['tag__name']: row['c']
        for row in TaggedStatus.objects.filter(content_type=variant_ct)
        .values('tag__name')
        .annotate(c=Count('object_id', distinct=True))
        if row['tag__name']
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

    from .models import TaggedStatus
    individual_ct = ContentType.objects.get_for_model(Individual)
    sample_ct = ContentType.objects.get_for_model(Sample)
    test_ct = ContentType.objects.get_for_model(Test)
    pipeline_ct = ContentType.objects.get_for_model(Pipeline)
    analysis_ct = ContentType.objects.get_for_model(Analysis)
    variant_ct = ContentType.objects.get_for_model(Variant)

    # Status (keyed by status name, counting distinct objects tagged with each status)
    status_counts = {s: 0 for s in Status.objects.filter(content_type=individual_ct).values_list('name', flat=True)}
    status_counts.update({
        row['tag__name']: row['c']
        for row in TaggedStatus.objects.filter(content_type=individual_ct)
        .values('tag__name').annotate(c=Count('object_id', distinct=True))
        if row['tag__name']
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

    # Is affected
    is_affected_counts = {True: 0, False: 0}
    is_affected_counts.update({
        row['is_affected']: row['c']
        for row in Individual.objects.values('is_affected').annotate(c=Count('id'))
    })

    # Is index
    is_index_counts = {True: 0, False: 0}
    is_index_counts.update({
        row['is_index']: row['c']
        for row in Individual.objects.values('is_index').annotate(c=Count('id'))
    })

    # Has Report
    has_report_counts = {
        'true': Individual.objects.filter(samples__tests__pipelines__analyses__reports__isnull=False).distinct().count(),
        'false': Individual.objects.filter(samples__tests__pipelines__analyses__reports__isnull=True).distinct().count()
    }

    # Has Request Form
    has_request_form_counts = {
        'true': Individual.objects.filter(analysis_request_forms__isnull=False).distinct().count(),
        'false': Individual.objects.filter(analysis_request_forms__isnull=True).distinct().count()
    }

    # Projects
    projects_counts = {p: 0 for p in Project.objects.values_list('name', flat=True)}
    projects_counts.update({
        row['projects__name']: row['c']
        for row in Individual.objects.filter(projects__isnull=False)
        .values('projects__name')
        .annotate(c=Count('id', distinct=True))
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
        row['tag__name']: row['c']
        for row in TaggedStatus.objects.filter(content_type=sample_ct)
        .values('tag__name').annotate(c=Count('object_id', distinct=True))
        if row['tag__name']
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
        row['tag__name']: row['c']
        for row in TaggedStatus.objects.filter(content_type=test_ct)
        .values('tag__name').annotate(c=Count('object_id', distinct=True))
        if row['tag__name']
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
        row['tag__name']: row['c']
        for row in TaggedStatus.objects.filter(content_type=pipeline_ct)
        .values('tag__name').annotate(c=Count('object_id', distinct=True))
        if row['tag__name']
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
        row['tag__name']: row['c']
        for row in TaggedStatus.objects.filter(content_type=analysis_ct)
        .values('tag__name').annotate(c=Count('object_id', distinct=True))
        if row['tag__name']
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
        row['tag__name']: row['c']
        for row in TaggedStatus.objects.filter(content_type=variant_ct)
        .values('tag__name').annotate(c=Count('object_id', distinct=True))
        if row['tag__name']
    })

    # ACMG classification (distinct individuals)
    classif_counts = {choice[0]: 0 for choice in VariantClassification.CLASSIFICATION_CHOICES}
    classif_counts.update({
        row['classification']: row['c']
        for row in VariantClassification.objects.values('classification')
        .annotate(c=Count('variant__individual_id', distinct=True))
        if row['classification']
    })


    # --- Lab App Setup/Installation Checks ---
    # Institution sub-filters (distinct individuals per city / speciality / center_name)
    institution_city_counts = {
        row['institution__city']: row['c']
        for row in Individual.objects.filter(institution__city__isnull=False)
        .exclude(institution__city='')
        .values('institution__city')
        .annotate(c=Count('id', distinct=True))
        if row['institution__city']
    }
    institution_speciality_counts = {
        row['institution__speciality']: row['c']
        for row in Individual.objects.filter(institution__speciality__isnull=False)
        .exclude(institution__speciality='')
        .values('institution__speciality')
        .annotate(c=Count('id', distinct=True))
        if row['institution__speciality']
    }
    institution_center_counts = {
        row['institution__center_name']: row['c']
        for row in Individual.objects.filter(institution__center_name__isnull=False)
        .exclude(institution__center_name='')
        .values('institution__center_name')
        .annotate(c=Count('id', distinct=True))
        if row['institution__center_name']
    }

    counts = {
        "status":                   status_counts,
        "sex":                      sex_counts,
        "is_alive":                 is_alive_counts,
        "is_affected":              is_affected_counts,
        "is_index":                 is_index_counts,
        "has_report":               has_report_counts,
        "has_request_form":         has_request_form_counts,
        "projects":                 projects_counts,
        "sample_type":              sample_type_counts,
        "sample_status":            sample_status_counts,
        "test_type":                test_type_counts,
        "test_status":              test_status_counts,
        "pipeline_type":            pipeline_type_counts,
        "pipeline_status":          pipeline_status_counts,
        "analysis_type":            analysis_type_counts,
        "analysis_status":          analysis_status_counts,
        "variant_type":             variant_type_counts,
        "variant_status":           variant_status_counts,
        "classification":           classif_counts,
        "institution_city":         institution_city_counts,
        "institution_speciality":   institution_speciality_counts,
        "institution_center":       institution_center_counts,
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

    from .models import TaggedStatus
    project_ct = ContentType.objects.get_for_model(Project)

    # Status (keyed by status name)
    status_counts = {s: 0 for s in Status.objects.filter(content_type=project_ct).values_list('name', flat=True)}
    status_counts.update({
        row['tag__name']: row['c']
        for row in TaggedStatus.objects.filter(content_type=project_ct)
        .values('tag__name').annotate(c=Count('object_id', distinct=True))
        if row['tag__name']
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
        
        from .models import TaggedStatus
        from django.contrib.contenttypes.models import ContentType as CT
        task_ct = CT.objects.get_for_model(Task)
        completed_task_ids = TaggedStatus.objects.filter(
            content_type=task_ct,
            tag__name__iexact="completed",
        ).values_list("object_id", flat=True)

        tasks = Task.objects.filter(assigned_to=self.request.user)
        context['my_tasks'] = tasks.exclude(
            pk__in=completed_task_ids
        ).order_by('due_date', '-priority')[:10]

        context['completed_tasks'] = tasks.filter(
            pk__in=completed_task_ids
        ).order_by('-id')[:5]

        # 1.5 Header Stats & breakdowns
        context['individual_count'] = Individual.objects.count()
        context['sample_count'] = Sample.objects.count()
        context['project_count'] = Project.objects.count()
        context['variant_count'] = Variant.objects.count()
        context['test_count'] = Test.objects.count()
        context['pipeline_count'] = Pipeline.objects.count()
        context['analysis_count'] = Analysis.objects.count()
        context['institution_count'] = Institution.objects.count()

        # Cached breakdowns reused from filter sidebars
        context['individual_filter_counts'] = _individual_filter_counts()
        context['project_filter_counts'] = _project_filter_counts()
        context['variant_filter_counts'] = _variant_filter_counts()

        # Lightweight institution breakdown (top cities)
        context['institution_city_counts'] = (
            Institution.objects.exclude(city__isnull=True)
            .exclude(city__exact="")
            .values('city')
            .annotate(c=Count('id'))
            .order_by('-c', 'city')[:10]
        )
        
        # Dashboard Widgets
        context["widgets"] = (
            self.request.user.dashboard_widgets.select_related("template").order_by("order")
        )
        context["marimo_service_url"] = getattr(
            settings, "MARIMO_SERVICE_URL", "http://127.0.0.1:8080"
        ).rstrip("/")

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
    
    
    def get_queryset(self):
        """
        Base queryset for the individual table & filters.
        Annotates first_institution_name so the Institution column can be sorted.
        """
        qs = super().get_queryset()
        qs = qs.prefetch_related("institution")

        # Per-individual aggregate timestamps for related objects that belong
        # exclusively to a single Individual (no shared multi-individual models).
        # We rely on domain timestamps rather than history tables so everything
        # can be expressed as ORM joins.
        qs = qs.annotate(
            first_institution_name=Min("institution__name"),
            individual_created_at=Max("created_at"),
            sample_last_date=Max("samples__receipt_date"),
            test_last_date=Max("samples__tests__performed_date"),
            pipeline_last_date=Max("samples__tests__pipelines__performed_date"),
            analysis_last_date=Max(
                "samples__tests__pipelines__analyses__performed_date"
            ),
            variant_last_dt=Max("variants__created_at"),
            report_last_dt=Max("samples__tests__pipelines__analyses__reports__created_at"),
        )

        # Last activity: pick the most downstream non-null timestamp in the
        # workflow order (Report -> Variant -> Analysis -> Pipeline -> Test
        # -> Sample -> Individual created). This avoids backend-specific
        # issues with Greatest across mixed date/datetime fields while still
        # giving a meaningful "last touched" value.
        qs = qs.annotate(
            last_activity=Coalesce(
                "report_last_dt",
                "variant_last_dt",
                Cast("analysis_last_date", output_field=DateTimeField()),
                Cast("pipeline_last_date", output_field=DateTimeField()),
                Cast("test_last_date", output_field=DateTimeField()),
                Cast("sample_last_date", output_field=DateTimeField()),
                "individual_created_at",
            )
        )

        return qs
    
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
            'statuses',
            'created_by',
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
        return super().get_queryset().select_related("individual").prefetch_related("statuses", "genes")

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


class MapVisualizationView(LoginRequiredMixin, TemplateView):
    template_name = "lab/visualizations.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Aggregate counts by institution city for different views:
        # - individuals: distinct individuals per city
        # - families: distinct family units per city (family if present, otherwise individual)
        # - probands: distinct index individuals (is_index=True) per city
        qs = (
            Individual.objects.filter(institution__city__isnull=False)
            .values("id", "family_id", "is_index", "institution__city")
            .order_by("institution__city")
        )

        city_individuals = {}
        city_families = {}
        city_probands = {}

        for row in qs:
            city = row["institution__city"]
            if city is None:
                continue
            indiv_id = row["id"]
            family_id = row["family_id"]
            is_index = row["is_index"]

            # Initialise per-city containers
            entry_indiv = city_individuals.setdefault(city, set())
            entry_fam = city_families.setdefault(city, set())
            entry_prob = city_probands.setdefault(city, set())

            # Individuals: distinct individuals per city
            entry_indiv.add(indiv_id)

            # Families: family if present, otherwise treat individual as a one-person family
            family_key = family_id if family_id is not None else f"self-{indiv_id}"
            entry_fam.add(family_key)

            # Probands: index individuals only
            if is_index:
                entry_prob.add(indiv_id)

        city_counts_individuals = {city: len(ids) for city, ids in city_individuals.items()}
        city_counts_families = {city: len(keys) for city, keys in city_families.items()}
        city_counts_probands = {city: len(ids) for city, ids in city_probands.items()}

        # Use individuals as the default sorted table display.
        city_counts_sorted = sorted(
            city_counts_individuals.items(), key=lambda item: item[1], reverse=True
        )

        context["city_counts_individuals"] = city_counts_individuals
        context["city_counts_families"] = city_counts_families
        context["city_counts_probands"] = city_counts_probands
        # Also provide a list sorted by count descending for display.
        context["city_counts_sorted"] = city_counts_sorted
        return context

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
            'individuals__statuses',
            'individuals__institution',
            'statuses',
            'created_by',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Paginate + filter + sort individuals within this project detail view
        from django.db.models import Q, Min

        request = self.request
        individuals_qs = (
            self.object.individuals.all()
            .prefetch_related("statuses", "institution")
        ).annotate(first_institution_name=Min("institution__name"))

        # Search by any ID value or institution name
        search = request.GET.get("search", "").strip()
        if search:
            individuals_qs = individuals_qs.filter(
                Q(cross_ids__id_value__icontains=search)
                | Q(institution__name__icontains=search)
            ).distinct()

        # Sorting
        sort = request.GET.get("sort") or "added"
        direction = request.GET.get("dir") or "desc"
        sort_map = {
            "primary": "id",  # approximate by PK
            "secondary": "id",
            "status": "id",  # status is now M2M, sort by id as fallback
            "institution": "first_institution_name",
            "sex": "sex",
            "added": "created_at",
        }
        sort_field = sort_map.get(sort, "created_at")
        if direction == "desc":
            sort_field = f"-{sort_field}"
        individuals_qs = individuals_qs.order_by(sort_field, "id")

        paginator = Paginator(individuals_qs, 25)
        page_number = request.GET.get("page") or 1
        context["individual_page"] = paginator.get_page(page_number)
        context["project_individuals_search"] = search
        context["project_individuals_sort"] = sort
        context["project_individuals_dir"] = direction
        return context


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
            'family__individuals__statuses',
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


class TaskDetailView(LoginRequiredMixin, DetailView):
    model = Task
    template_name = "lab/task_detail.html"
    context_object_name = "task"

    def get_queryset(self):
        return Task.objects.select_related(
            "assigned_to", "created_by", "project", "content_type"
        ).prefetch_related("statuses", "notes__user")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = self.object

        history_qs = task.history.all().select_related("history_user")[:20]
        history_list = list(history_qs)
        for i, record in enumerate(history_list):
            if record.history_type == "~":
                prev = history_list[i + 1] if i + 1 < len(history_list) else None
                record.diff_display = self._get_field_diff(record, prev) if prev else {}
            else:
                record.diff_display = {}
        context["history_records"] = history_list

        from django.db.models import Q
        context["notes"] = task.notes.filter(
            Q(private_owner__isnull=True) | Q(private_owner=self.request.user)
        ).select_related("user").order_by("id")

        context["edit_mode"] = False
        context["now"] = timezone.now()
        return context

    def _get_field_diff(self, new_hist, old_hist):
        if not old_hist:
            return {}
        changes = {}
        ignore = {"history_id", "history_date", "history_type", "history_user", "history_change_reason", "id"}
        for field in new_hist._meta.fields:
            name = field.name
            if name in ignore:
                continue
            new_val = getattr(new_hist, name, None)
            old_val = getattr(old_hist, name, None)
            if new_val != old_val:
                label = name.replace("_", " ").title()
                changes[label] = f"'{old_val if old_val is not None else '(empty)'}' → '{new_val if new_val is not None else '(empty)'}'"
        return changes


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
                    
                    individual.save()
                    individual.institution.set(inline_form.cleaned_data['institution'])
                    individual.hpo_terms.set(inline_form.cleaned_data['hpo_terms'])
                    # Set statuses from the form
                    selected_statuses = inline_form.cleaned_data.get('statuses')
                    if selected_statuses:
                        individual.statuses.set(selected_statuses)
                    elif not individual.statuses.exists():
                        from .models import Status
                        default_status = Status.objects.first()
                        if default_status:
                            individual.statuses.add(default_status)
                    
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
        
        if task.assigned_to != request.user and not request.user.is_superuser:
            return HttpResponseForbidden("You are not assigned to this task.")
            
        task.complete(request.user)
        
        if request.htmx:
            response = HttpResponse("")
            response["HX-Trigger"] = "taskChanged"
            return response
        return redirect("lab:task_detail", pk=pk)


class ReopenTaskView(LoginRequiredMixin, TemplateView):
    def post(self, request, pk):
        from .models import Task
        task = get_object_or_404(Task, pk=pk)

        # Permission check
        if task.assigned_to != request.user and not request.user.is_superuser:
            return HttpResponseForbidden("You cannot reopen this task.")

        # Reopen logic
        if task.statuses.filter(name__iexact="completed").exists():
            if task.previous_status:
                task.statuses.set([task.previous_status])
                task.previous_status = None
            else:
                pending_status = (
                    Status.objects.filter(name__iexact="pending").first()
                    or Status.objects.first()
                )
                if pending_status:
                    task.statuses.set([pending_status])

            task.save(update_fields=["previous_status"])

            if request.htmx:
                response = HttpResponse("")
                response["HX-Trigger"] = "taskChanged"
                return response
            return redirect("lab:task_detail", pk=pk)

        if request.htmx:
            return HttpResponse("")
        return redirect("lab:task_detail", pk=pk)

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
            status = ", ".join(individual.statuses.values_list("name", flat=True))
            
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


# --- API for Marimo ---
from django.apps import apps
from django.views import generic
from django.views.decorators.http import require_http_methods, require_POST
from .jwt_utils import issue_plot_token, verify_plot_token

@login_required
def issue_plot_token_view(request):
    token = issue_plot_token(request.user)
    expires = int(getattr(settings, "MARIMO_PLOT_TOKEN_MAX_AGE", 900))
    return JsonResponse({"token": token, "expires_in": expires})

def generic_plot_data(request):
    user = request.user
    if not user.is_authenticated:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            try:
                user = verify_plot_token(token)
            except Exception as e:
                logger.warning("plot-data: bearer token verification failed (%s)", e)
                return JsonResponse({"error": str(e)}, status=401)
        else:
            logger.warning("plot-data: unauthenticated request with no bearer token")
            return JsonResponse({"error": "Unauthorized"}, status=401)

    allowed_models = getattr(settings, "PLOT_ALLOWED_MODELS", [])
    model_name = request.GET.get("model")
    if model_name not in allowed_models:
        logger.warning("plot-data: disallowed model requested: %s", model_name)
        return JsonResponse({"error": "Model not allowed"}, status=403)

    try:
        model = apps.get_model("lab", model_name)
    except LookupError:
        try:
            model = apps.get_model("variant", model_name)
        except LookupError:
            return JsonResponse({"error": f"Model {model_name} not found"}, status=400)

    query_str = request.GET.get("config") or request.GET.get("query") or "{}"
    try:
        config = json.loads(query_str)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid query config"}, status=400)

    qs = model.objects.all()

    filters = _plot_config_filters(config)
    if filters:
        qs = qs.filter(**filters)

    values = config.get("values") or []
    if values:
        qs = qs.values(*values)

    annotate = config.get("annotate") or {}
    if annotate:
        try:
            annotations = _plot_build_annotations(annotate)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        qs = qs.annotate(**annotations)

    qs = _plot_ensure_dict_rows(qs)
    data = list(qs)
    return JsonResponse({"data": data, "model": model_name, "record_count": len(data)})

class PlotGalleryView(LoginRequiredMixin, generic.ListView):
    model = PlotTemplate
    template_name = 'lab/gallery.html'
    context_object_name = 'templates'

    def get_queryset(self):
        return super().get_queryset().filter(is_published=True)

@login_required
@require_POST
def add_widget(request, pk):
    template = get_object_or_404(PlotTemplate, pk=pk)
    # Check if user already has this template on dashboard
    if not DashboardWidget.objects.filter(user=request.user, template=template).exists():
        # Add to dashboard at the end
        last_order = DashboardWidget.objects.filter(user=request.user).aggregate(max_order=Max("order"))["max_order"] or 0
        DashboardWidget.objects.create(
            user=request.user,
            template=template,
            order=last_order + 1
        )
    # HTMX response to show success checkmark or text swap
    return HttpResponse('<span class="text-success"><i class="fa-solid fa-check"></i> Added</span>')

@login_required
@require_POST
def remove_widget(request, pk):
    # pk is the widget ID (or template ID if we want, but widget ID is safer)
    widget = get_object_or_404(DashboardWidget, pk=pk, user=request.user)
    widget.delete()
    return HttpResponse("") # HTMX will swap out the element (outerHTML)

@login_required
@require_http_methods(["PATCH"])
def reorder_widgets(request):
    try:
        data = json.loads(request.body)
        order_list = data.get("order", [])
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # Perform bulk update
    widgets = []
    for index, widget_id in enumerate(order_list):
        try:
            widget = DashboardWidget.objects.get(pk=widget_id, user=request.user)
            widget.order = index
            widgets.append(widget)
        except DashboardWidget.DoesNotExist:
            pass

    if widgets:
        DashboardWidget.objects.bulk_update(widgets, ['order'])

    return JsonResponse({"status": "success"})


# --- Admin Authoring UX Endpoints ---
import os
from django.contrib.admin.views.decorators import staff_member_required

@staff_member_required
def list_notebook_files(request):
    """Returns a list of .py notebook files in the notebooks directory."""
    notebooks_dir = getattr(settings, 'MARIMO_NOTEBOOKS_DIR', settings.BASE_DIR / 'lab' / 'notebooks')
    files = []
    if os.path.exists(notebooks_dir):
        for f in os.listdir(notebooks_dir):
            if f.endswith('.py') and not f.startswith('_'):
                files.append(f)
    return JsonResponse({"notebooks": sorted(files)})

@staff_member_required
@require_POST
def preview_plot_data(request):
    """Executes a JSON query payload exactly as the API would, for testing/validation."""
    try:
        payload = json.loads(request.body)
        model_name = payload.get('target_model')
        query_config = payload.get('query_config', {})
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    allowed_models = getattr(settings, 'PLOT_ALLOWED_MODELS', [])
    if model_name not in allowed_models:
        return JsonResponse({"error": f"Model {model_name} not allowed"}, status=400)
        
    try:
        model = apps.get_model('lab', model_name)
    except LookupError:
        try:
            model = apps.get_model('variant', model_name)
        except LookupError:
            return JsonResponse({"error": f"Model {model_name} not found"}, status=400)
    
    qs = model.objects.all()

    filters = _plot_config_filters(query_config)
    if filters:
        try:
            qs = qs.filter(**filters)
        except Exception as e:
            return JsonResponse({"error": f"Filter error: {str(e)}"}, status=400)

    values = query_config.get("values") or []
    if values:
        try:
            qs = qs.values(*values)
        except Exception as e:
            return JsonResponse({"error": f"Values error: {str(e)}"}, status=400)

    annotate = query_config.get("annotate") or {}
    if annotate:
        try:
            annotations = _plot_build_annotations(annotate)
            qs = qs.annotate(**annotations)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        except Exception as e:
            return JsonResponse({"error": f"Annotate error: {str(e)}"}, status=400)

    try:
        qs = _plot_ensure_dict_rows(qs)
        data = list(qs[:5])
    except Exception as e:
        return JsonResponse({"error": f"Database execution error: {str(e)}"}, status=400)

    return JsonResponse({"data": data, "record_count": qs.count()})


@staff_member_required
def marimo_proxy(request, path=""):
    """
    Send staff to the local Marimo *edit* server with a long-lived JWT on the query string.

    Use GET params Marimo understands (e.g. file=status_bar.py). Cross-origin cookies do not
    reach :8081, so the token is carried in the URL; notebooks read it via mo.query_params().
    """
    from .jwt_utils import issue_editor_plot_token

    marimo_base = getattr(settings, "MARIMO_EDITOR_URL", "http://127.0.0.1:8081").rstrip("/")
    params = request.GET.copy()
    params["token"] = issue_editor_plot_token(request.user)
    return redirect(f"{marimo_base}/?{params.urlencode()}")


@login_required
def marimo_run_proxy(request):
    """
    Send the user to the Marimo *run* server (dashboard / read-only app) with a plot JWT.

    Opening http://localhost:8080/?file=… alone does not include a Django JWT, so plot cells
    stop with auth. This view adds token= for mo.query_params() (Marimo does not strip it).
    """
    from pathlib import Path

    from django.http import HttpResponseBadRequest

    raw = (request.GET.get("file") or "").strip()
    if not raw:
        return HttpResponseBadRequest("Missing required query parameter: file")
    safe_name = Path(raw).name
    if safe_name != raw:
        return HttpResponseBadRequest("file= must be a basename only (e.g. sunburst.py)")
    nb_dir = getattr(settings, "MARIMO_NOTEBOOKS_DIR", None)
    if nb_dir is not None and not (Path(nb_dir) / safe_name).is_file():
        return HttpResponseBadRequest("Notebook file not found in MARIMO_NOTEBOOKS_DIR")

    marimo_base = getattr(settings, "MARIMO_SERVICE_URL", "http://127.0.0.1:8080").rstrip("/")
    token = issue_plot_token(request.user)
    from urllib.parse import urlencode

    return redirect(f"{marimo_base}/?{urlencode({'file': safe_name, 'token': token})}")
