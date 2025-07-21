from django.apps import apps
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseBadRequest
from django.db.models import Q
from django.contrib.contenttypes.models import ContentType
import json

# Import models
from .models import Individual

# Import HPO visualization functions
from .visualization.hpo_network_visualization import (
    process_hpo_data,
    plotly_hpo_network,
)


FILTER_CONFIG = {
    "Term": {
        "app_label": "ontologies",
        "search_fields": [
            "identifier",
            "label",
        ],
        "filters": {},
    },
    "Individual": {
        "app_label": "lab",
        "search_fields": ["full_name", "cross_ids__id_value", "family__family_id"],
        "filters": {
            "Institution": "institution__pk",
            "Term": "hpo_terms__pk",
            "Sample": "samples__pk",
        },
    },
    "Sample": {
        "app_label": "lab",
        "search_fields": ["sample_type__name", "id"],
        "filters": {
            "Individual": "individual__pk",
            "Institution": "individual__institution__pk",
            "Term": "individual__hpo_terms__pk",
            "Test": "tests",
        },
    },
    "Institution": {
        "app_label": "lab",
        "search_fields": ["name", "contact"],
        "filters": {},  # Nothing filters an Institution in this example
    },
    "Test": {
        "app_label": "lab",
        "search_fields": ["test_type__name"],
        "filters": {
            "Individual": "sample__individual__pk",
            "Sample": "sample__pk",
            "Institution": "sample__individual__institution__pk",
        },
    },
    "Analysis": {
        "app_label": "lab",
        "search_fields": ["type__name", "test__sample__individual__full_name"],
        "filters": {
            "Test": "test__pk",
            "Sample": "test__sample__sample_type__pk",  # Filter by SampleType
            "Individual": "test__sample__individual__pk",
        },
    },
    "Project": {
        "app_label": "lab",
        "search_fields": ["name", "description"],
        # Projects are a top-level item in this schema and are not filtered by other models.
        "filters": {},
    },
    "Task": {
        "app_label": "lab",
        "search_fields": ["title", "description"],
        "filters": {
            # Standard foreign key relationship
            "Project": "project__pk",
            "Institution": [
                {
                    "link_model": "Individual",
                    "path_from_link_model": "institution__pk",
                },
                {
                    "link_model": "Sample",
                    "path_from_link_model": "individual__institution__pk",
                },
                {
                    "link_model": "Test",
                    "path_from_link_model": "sample__individual__institution__pk",
                },
            ],
            "Individual": [
                {
                    "link_model": "Individual",
                    "path_from_link_model": "pk",
                },
                {
                    "link_model": "Sample",
                    "path_from_link_model": "individual__pk",
                },
                {
                    "link_model": "Test",
                    "path_from_link_model": "sample__individual__pk",
                },
            ],
            "Sample": [
                {
                    "link_model": "Sample",
                    "path_from_link_model": "pk",
                },
                {
                    "link_model": "Test",
                    "path_from_link_model": "pk",
                },
            ],
            "Test": [
                {
                    "link_model": "Test",
                    "path_from_link_model": "pk",
                },
            ],
        },
    },
}


@login_required
def index(request):
    context = {}
    print("index 00")

    if request.headers.get("HX-Request"):
        print("index 01")
        return render(request, "lab/index.html#index", context)
    print("index 02")
    return render(request, "lab/index.html", context)


def _get_filter_search_term(request, filter_model_name):
    """Get the filter value from the request for a given filter model name."""
    return request.GET.get(f"filter_{filter_model_name.lower()}", "").strip()


def _apply_direct_field_filter(queryset, orm_path, filter_search_term):
    """Apply a direct, exact filter using the term and path."""
    return queryset.filter(**{orm_path: filter_search_term})


def _get_pks_to_filter_by(filter_model_name, filter_search_term):
    """Determine PKs to filter by, using digit or text search."""
    if filter_search_term.isdigit():
        return [int(filter_search_term)]
    filter_model_config = FILTER_CONFIG.get(filter_model_name, {})
    filter_app_label = filter_model_config.get("app_label", "lab")
    filter_model = apps.get_model(app_label=filter_app_label, model_name=filter_model_name)
    search_fields = filter_model_config.get("search_fields", [])
    if search_fields:
        q_objects = Q()
        for field in search_fields:
            q_objects |= Q(**{f"{field}__icontains": filter_search_term})
        return list(
            filter_model.objects.filter(q_objects)
            .values_list("pk", flat=True)
            .distinct()
        )
    return []


def _apply_orm_path_filter(queryset, orm_path, pks_to_filter_by, filter_model_name):
    """Apply the filter to the queryset, handling list, tuple, and string cases for orm_path."""
    if isinstance(orm_path, list):
        combined_q = Q()
        for path_config in orm_path:
            link_model_name = path_config["link_model"]
            link_model_app_label = FILTER_CONFIG.get(link_model_name, {}).get("app_label", "lab")
            link_model = apps.get_model(app_label=link_model_app_label, model_name=link_model_name)
            path_from_link = path_config["path_from_link_model"]
            link_model_pks = link_model.objects.filter(
                **{f"{path_from_link}__in": pks_to_filter_by}
            ).values_list("pk", flat=True)
            content_type = ContentType.objects.get_for_model(link_model)
            combined_q |= Q(content_type=content_type, object_id__in=list(link_model_pks))
        if combined_q:
            return queryset.filter(combined_q)
        else:
            return queryset.none()
    elif isinstance(orm_path, tuple):
        filter_model_config = FILTER_CONFIG.get(filter_model_name, {})
        filter_app_label = filter_model_config.get("app_label", "lab")
        filter_model = apps.get_model(app_label=filter_app_label, model_name=filter_model_name)
        content_type_field, object_id_field = orm_path
        content_type = ContentType.objects.get_for_model(filter_model)
        return queryset.filter(
            **{
                content_type_field: content_type,
                f"{object_id_field}__in": pks_to_filter_by,
            }
        )
    else:
        return queryset.filter(**{f"{orm_path}__in": pks_to_filter_by})


def _apply_own_search_filter(queryset, filter_config, request):
    own_search_term = request.GET.get("search", "").strip()
    if own_search_term:
        own_search_fields = filter_config.get("search_fields", [])
        if own_search_fields:
            q_objects = Q()
            for field in own_search_fields:
                q_objects |= Q(**{f"{field}__icontains": own_search_term})
            queryset = queryset.filter(q_objects)
    return queryset


def apply_filters(request, target_model_name, queryset):
    """
    Applies filters. Now handles direct field filtering (e.g., by name)
    in addition to PK and text-based searches.
    """
    filter_config = FILTER_CONFIG.get(target_model_name, {})
    for filter_model_name, orm_path in filter_config.get("filters", {}).items():
        filter_search_term = _get_filter_search_term(request, filter_model_name)
        if filter_search_term:
            source_filter_config = FILTER_CONFIG.get(filter_model_name, {})
            # NEW: Check if the filter comes from a field-based select dropdown
            if "select_options_from_field" in source_filter_config:
                queryset = _apply_direct_field_filter(queryset, orm_path, filter_search_term)
            else:
                pks_to_filter_by = _get_pks_to_filter_by(filter_model_name, filter_search_term)
                if not pks_to_filter_by:
                    return queryset.none()
                queryset = _apply_orm_path_filter(queryset, orm_path, pks_to_filter_by, filter_model_name)
    queryset = _apply_own_search_filter(queryset, filter_config, request)
    return queryset.distinct()


@login_required
def generic_search(request):
    target_app_label = request.GET.get("app_label", "lab").strip()  # Get app_label
    target_model_name = request.GET.get("model_name", "").strip()
    if not target_model_name:
        return HttpResponseBadRequest("Model not specified.")

    target_model = apps.get_model(
        app_label=target_app_label, model_name=target_model_name
    )

    filtered_items = apply_filters(
        request, target_model_name, target_model.objects.all()
    )

    num_items = filtered_items.count()

    # Pagination
    page = request.GET.get("page")
    paginator = Paginator(filtered_items, 12)
    paged_items = paginator.get_page(page)

    # The rest of the view remains the same...
    own_search_term = request.GET.get("search", "").strip()
    response = render(
        request,
        "lab/index.html#generic-search-results",
        {
            "items": paged_items,
            "num_items": num_items,
            "search": own_search_term,
            "app_label": target_app_label,
            "model_name": target_model_name,
            "all_filters": {
                k: v for k, v in request.GET.items() if k.startswith("filter_")
            },
        },
    )
    return response


@login_required
def hpo_network_visualization(request):
    initial_queryset = Individual.objects.all()
    filtered_individuals = apply_filters(request, "Individual", initial_queryset)
    threshold = request.GET.get("threshold", 10)
    if threshold:
        threshold = int(threshold)
    else:
        threshold = 10
    consolidated_counts, graph, hpo = process_hpo_data(
        filtered_individuals, threshold=threshold
    )
    fig, _ = plotly_hpo_network(graph, hpo, consolidated_counts, min_count=1)
    plot_json = json.dumps(fig.to_dict())
    return render(
        request,
        "lab/index.html#hpo-network-visualization",
        {
            "plot_json": plot_json,
            "threshold": threshold,
            "term_count": len(consolidated_counts),
            "individuals": filtered_individuals,
            "individual_count": len(filtered_individuals),
        },
    )
