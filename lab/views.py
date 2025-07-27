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

from .filters import apply_filters, FILTER_CONFIG


@login_required
def index(request):
    context = {}
    print("index 00")

    if request.headers.get("HX-Request"):
        print("index 01")
        return render(request, "lab/index.html#index", context)
    print("index 02")
    return render(request, "lab/index.html", context)


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