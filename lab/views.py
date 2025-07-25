from django.apps import apps
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseBadRequest
from django.db.models import Q
from django.contrib.contenttypes.models import ContentType
import json
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from .models import Note
from django.contrib.contenttypes.models import ContentType

from django.views.decorators.vary import vary_on_headers
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
        "search_fields": ["identifier", "label"],
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
        "select_fields": {
            "sample_type": {
                "field_path": "samples__sample_type__name",
                "label": "Sample Type",
                "select_filter_path": "samples__sample_type__name",
            },
        },
    },
    "Sample": {
        "app_label": "lab",
        "search_fields": ["sample_type__name", "id"],
        "filters": {
            "Individual": "individual__pk",
            "Institution": "individual__institution__pk",
            "Term": "individual__hpo_terms__pk",
            "Test": "tests__pk",
        },
        "select_fields": {
            "sample_type": {
                "field_path": "sample_type__name",
                "label": "Sample Type",
                "select_filter_path": "sample_type__name",
            },
        },
    },
    "Test": {
        "app_label": "lab",
        "search_fields": ["test_type__name"],
        "filters": {
            "Individual": "sample__individual__pk",
            "Sample": "sample__pk",
            "Institution": "sample__individual__institution__pk",
        },
        "select_fields": {
            "sample_type": {
                "field_path": "sample__sample_type__name",
                "label": "Sample Type",
                "select_filter_path": "sample__sample_type__name",
            },
            "analysis_type": {
                "field_path": "analyses__type__name",
                "label": "Analysis Type",
                "select_filter_path": "analyses__type__name",
            },
            "test_type": {
                "field_path": "test_type__name",
                "label": "Test Type",
                "select_filter_path": "test_type__name",
            },
        },
    },
    "Analysis": {
        "app_label": "lab",
        "search_fields": ["type__name", "test__sample__individual__full_name"],
        "filters": {
            "Test": "test__pk",
            "Sample": "test__sample__sample_type__pk",
            "Individual": "test__sample__individual__pk",
        },
        "select_fields": {
            "sample_type": {
                "field_path": "test__sample__sample_type__name",
                "label": "Sample Type",
                "select_filter_path": "test__sample__sample_type__name",
            },
            "analysis_type": {
                "field_path": "type__name",
                "label": "Analysis Type",
                "select_filter_path": "type__name",
            },
        },
    },
    "Institution": {
        "app_label": "lab",
        "search_fields": ["name", "contact"],
        "filters": {},
    },
    "Project": {
        "app_label": "lab",
        "search_fields": ["name", "description"],
        "filters": {},
    },
    "Task": {
        "app_label": "lab",
        "search_fields": ["title", "description"],
        "filters": {
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
    filter_model = apps.get_model(
        app_label=filter_app_label, model_name=filter_model_name
    )
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
            link_model_app_label = FILTER_CONFIG.get(link_model_name, {}).get(
                "app_label", "lab"
            )
            link_model = apps.get_model(
                app_label=link_model_app_label, model_name=link_model_name
            )
            path_from_link = path_config["path_from_link_model"]
            link_model_pks = link_model.objects.filter(
                **{f"{path_from_link}__in": pks_to_filter_by}
            ).values_list("pk", flat=True)
            content_type = ContentType.objects.get_for_model(link_model)
            combined_q |= Q(
                content_type=content_type, object_id__in=list(link_model_pks)
            )
        if combined_q:
            return queryset.filter(combined_q)
        else:
            return queryset.none()
    elif isinstance(orm_path, tuple):
        filter_model_config = FILTER_CONFIG.get(filter_model_name, {})
        filter_app_label = filter_model_config.get("app_label", "lab")
        filter_model = apps.get_model(
            app_label=filter_app_label, model_name=filter_model_name
        )
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


# NEW HELPER FUNCTION
def _get_select_field_config(field_name, target_model_name=None):
    """
    Finds the configuration for a select field.
    If target_model_name is given, only look in that model's config.
    """
    if target_model_name:
        config = FILTER_CONFIG.get(target_model_name, {})
        if field_name in config.get("select_fields", {}):
            return target_model_name, config["select_fields"][field_name]
        return None, None
    else:
        for model_name, config in FILTER_CONFIG.items():
            if field_name in config.get("select_fields", {}):
                return model_name, config["select_fields"][field_name]
        return None, None


# REPLACE apply_filters with this new version
def apply_filters(request, target_model_name, queryset, exclude_filter=None):
    """
    Applies search and cross-model filters to a given queryset.
    Handles both generic text search and exact-match select filters.
    """
    target_config = FILTER_CONFIG.get(target_model_name, {})

    # Handle the component's own text search (from generic-search partial)
    own_search_term = request.GET.get("search") or request.GET.get(
        f"filter_{target_model_name.lower()}"
    )
    if own_search_term:
        own_search_fields = target_config.get("search_fields", [])
        if own_search_fields:
            q_objects = Q()
            for field in own_search_fields:
                q_objects |= Q(**{f"{field}__icontains": own_search_term})
            queryset = queryset.filter(q_objects)

    # Handle all cross-model filters from URL params (filter_*)
    active_filters = {
        k.replace("filter_", ""): v
        for k, v in request.GET.items()
        if k.startswith("filter_") and v and k.replace("filter_", "") != exclude_filter
    }

    for filter_key, filter_value in active_filters.items():
        # Only look for select field config in the target model
        source_model_name, select_config = _get_select_field_config(
            filter_key, target_model_name
        )

        # A) If it's a select filter, apply an exact match
        print(select_config)
        if select_config:
            select_filter_path = select_config.get("select_filter_path")
            if select_filter_path:
                queryset = queryset.filter(
                    **{f"{select_filter_path}__exact": filter_value}
                )
            else:
                continue
        # B) If it's a text-search filter from another model, use 'icontains'
        else:
            orm_path = target_config.get("filters", {}).get(filter_key.title())
            if isinstance(orm_path, str):
                filter_model_name = filter_key.title()
                filter_model_config = FILTER_CONFIG.get(filter_model_name, {})
                search_fields = filter_model_config.get("search_fields", [])
                if not search_fields:
                    continue

                filter_app_label = filter_model_config.get("app_label", "lab")
                filter_model = apps.get_model(
                    app_label=filter_app_label, model_name=filter_model_name
                )

                q_objects = Q()
                for field in search_fields:
                    q_objects |= Q(**{f"{field}__icontains": filter_value})

                pks_to_filter_by = list(
                    filter_model.objects.filter(q_objects)
                    .values_list("pk", flat=True)
                    .distinct()
                )
                if not pks_to_filter_by:
                    return queryset.none()
                queryset = queryset.filter(**{f"{orm_path}__in": pks_to_filter_by})
            else:
                # skip/ignore if orm_path is not a string (e.g., list/tuple/None)
                continue

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
def generic_search_page(request):
    """
    This view ONLY handles infinite scroll pagination.
    It returns a simple list of items, not an OOB response.
    """
    target_app_label = request.GET.get("app_label", "lab").strip()
    target_model_name = request.GET.get("model_name", "").strip()
    if not target_model_name:
        return HttpResponseBadRequest("Model not specified.")

    target_model = apps.get_model(
        app_label=target_app_label, model_name=target_model_name
    )

    filtered_items = apply_filters(
        request, target_model_name, target_model.objects.all()
    )

    # Pagination
    page = request.GET.get("page")
    paginator = Paginator(filtered_items, 12)
    paged_items = paginator.get_page(page)

    card_partial = request.GET.get("card", "card")
    context = {
        "items": paged_items,
        "model_name": target_model_name,
        "app_label": target_app_label,
        "all_filters": {
            k: v for k, v in request.GET.items() if k.startswith("filter_")
        },
        "card": card_partial,
    }
    return render(request, "lab/partials/_infinite_scroll_items.html", context)


@login_required
@vary_on_headers("HX-Request")
def generic_detail(request):
    target_app_label = request.GET.get("app_label", "lab").strip()
    target_model_name = request.GET.get("model_name", "").strip()
    pk = request.GET.get("pk")
    if not target_model_name or not pk:
        return HttpResponseBadRequest("Model or pk not specified.")

    target_model = apps.get_model(app_label=target_app_label, model_name=target_model_name)
    obj = get_object_or_404(target_model, pk=pk)

    template_base = f"lab/{target_model_name.lower()}.html"
    if request.htmx:
        # Render only the detail partial for htmx requests
        template_name = f"{template_base}#detail"
    else:
        # Render the full template for non-htmx requests
        template_name = template_base
    return render(request, template_name, {"item": obj, "model_name": target_model_name, "app_label": target_app_label})


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


@login_required
def get_select_options(request):
    model_name = request.GET.get("model_name")
    field_name = request.GET.get("field_name")
    selected_value = request.GET.get("selected_value")

    config = FILTER_CONFIG.get(model_name, {})
    if not config:
        return HttpResponseBadRequest("Model not configured.")

    select_config = config.get("select_fields", {}).get(field_name, {})
    field_path = select_config.get("field_path")
    select_filter_path = select_config.get("select_filter_path", field_path)

    model_class = apps.get_model(
        app_label=config.get("app_label"), model_name=model_name
    )
    if not all([field_name, model_class, select_filter_path]):
        return HttpResponseBadRequest("Invalid request for select options.")

    # Apply all filters *except* the one we are fetching options for
    filtered_qs = apply_filters(
        request, model_name, model_class.objects.all(), exclude_filter=field_name
    )
    options = (
        filtered_qs.order_by(select_filter_path)
        .values_list(select_filter_path, flat=True)
        .filter(**{f"{select_filter_path}__isnull": False})
        .distinct()
    )

    return render(
        request,
        "lab/index.html#select-options",
        {
            "options": list(options),
            "label": select_config.get("label", ""),
            "selected_value": selected_value,
        },
    )


@login_required
def note_list(request):
    object_id = request.GET.get("object_id")
    content_type_id = request.GET.get("content_type")
    content_type = get_object_or_404(ContentType, id=content_type_id)
    obj = content_type.get_object_for_this_type(id=object_id)
    return render(
        request,
        "lab/note.html#note-list",
        {
            "object": obj,
            "content_type": content_type_id,
            "user": request.user,
        },
    )


@login_required
@require_POST
def note_create(request):
    content_type_id = request.POST.get("content_type")
    object_id = request.POST.get("object_id")
    content = request.POST.get("content")
    content_type = get_object_or_404(ContentType, id=content_type_id)
    obj = content_type.get_object_for_this_type(id=object_id)
    note = Note.objects.create(
        content=content,
        user=request.user,
        content_type=content_type,
        object_id=object_id,
    )
    return render(
        request,
        "lab/note.html#note-list",
        {
            "object": obj,
            "content_type": content_type_id,
            "user": request.user,
        },
    )


@login_required
def note_count(request):
    object_id = request.GET.get("object_id")
    content_type_id = request.GET.get("content_type")
    content_type = get_object_or_404(ContentType, id=content_type_id)
    obj = content_type.get_object_for_this_type(id=object_id)
    return render(
        request,
        "lab/note.html#note-summary",
        {
            "object": obj,
            "content_type": content_type_id,
            "user": request.user,
        },
    )


@login_required
@require_POST
def note_delete(request, pk):
    note = get_object_or_404(Note, pk=pk, user=request.user)
    content_type_id = note.content_type.id
    object_id = note.object_id
    obj = note.content_object
    note.delete()
    return render(
        request,
        "lab/note.html#note-list",
        {
            "object": obj,
            "content_type": content_type_id,
            "user": request.user,
        },
    )
