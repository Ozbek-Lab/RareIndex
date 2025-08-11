from django.apps import apps
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.db.models import Q
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
import json
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from .models import Note, StatusLog, Status

from django.views.decorators.vary import vary_on_headers
from django.template.loader import render_to_string
from django.template.response import TemplateResponse

# Import models
from .models import Individual, Test, Analysis, Sample, Task, Note

# Import forms
from .forms import NoteForm

# Import HPO visualization functions
from .visualization.hpo_network_visualization import (
    process_hpo_data,
    plotly_hpo_network,
)

from .filters import apply_filters, FILTER_CONFIG, get_available_statuses

# Import SQL agent for natural language search
from .sql_agent import query_natural_language, execute_safe_sql


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
    card_partial = request.GET.get("card", "card")
    view_mode = request.GET.get("view_mode", "cards")
    icon_class = request.GET.get("icon_class", "fa-magnifying-glass")
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
            "view_mode": view_mode,
            "card": card_partial,
            "icon_class": icon_class,
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
    view_mode = request.GET.get("view_mode", "cards")
    context = {
        "items": paged_items,
        "model_name": target_model_name,
        "app_label": target_app_label,
        "all_filters": {
            k: v for k, v in request.GET.items() if k.startswith("filter_")
        },
        "view_mode": view_mode,
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

    target_model = apps.get_model(
        app_label=target_app_label, model_name=target_model_name
    )

    obj = get_object_or_404(target_model, pk=pk)

    template_base = f"lab/{target_model_name.lower()}.html"
    context = {
        "item": obj,
        "model_name": target_model_name,
        "app_label": target_app_label,
    }

    if target_model_name == "Individual":
        context["tests"] = [test for sample in obj.samples.all() for test in sample.tests.all()]
        context["analyses"] = [analysis for test in context["tests"] for analysis in test.analyses.all()]
    elif target_model_name == "Sample":
        context["analyses"] = [analysis for test in obj.tests.all() for analysis in test.analyses.all()]

    if request.htmx:
        # For HTMX requests, return only the detail partial
        return render(request, f"{template_base}#detail", context)
    else:
        # For direct loads, render the main index page and inject the detail content
        detail_html = render_to_string(
            f"{template_base}#detail", context=context, request=request
        )
        return render(request, "lab/index.html", {"initial_detail_html": detail_html})


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

    # Handle multiple selected values - if it's a JSON array, parse it
    if selected_value and selected_value.startswith('[') and selected_value.endswith(']'):
        try:
            import json
            selected_value = json.loads(selected_value)
        except json.JSONDecodeError:
            selected_value = [selected_value]
    elif selected_value:
        # Single value - convert to list for consistency
        selected_value = [selected_value]
    else:
        selected_value = []

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
def get_status_buttons(request):
    """Get status buttons for a specific model"""
    model_name = request.GET.get("model_name")
    app_label = request.GET.get("app_label", "lab")
    selected_statuses = request.GET.get("selected_statuses")

    # Handle multiple selected statuses - if it's a JSON array, parse it
    if selected_statuses and selected_statuses.startswith('[') and selected_statuses.endswith(']'):
        try:
            import json
            selected_statuses = json.loads(selected_statuses)
        except json.JSONDecodeError:
            selected_statuses = [selected_statuses]
    elif selected_statuses:
        # Single value - convert to list for consistency
        selected_statuses = [selected_statuses]
    else:
        selected_statuses = []

    if not model_name:
        return HttpResponseBadRequest("Model not specified.")

    # Get available statuses for this model
    statuses = get_available_statuses(model_name, app_label)

    return render(
        request,
        "lab/index.html#status-buttons",
        {
            "statuses": statuses,
            "selected_statuses": selected_statuses,
            "model_name": model_name,
        },
    )


@login_required
def note_create(request):
    """Create a new note for a specific object"""
    if request.method == "POST":
        content_type_str = request.POST.get("content_type")
        object_id = request.POST.get("object_id")

        # Get the content type and object
        model = apps.get_model("lab", content_type_str.capitalize())
        content_type = ContentType.objects.get_for_model(model)
        obj = model.objects.get(id=object_id)

        # Create the note
        Note.objects.create(
            content=request.POST.get("content"),
            user=request.user,
            content_type=content_type,
            object_id=object_id,
        )

        # Return the updated list
        return TemplateResponse(
            request,
            "lab/note.html#list",
            {
                "object": obj,
                "content_type": content_type_str,
                "user": request.user,
            },
        )

    # For GET requests, return the form
    content_type_str = request.GET.get("content_type")
    object_id = request.GET.get("object_id")

    # Get the content type and object
    model = apps.get_model("lab", content_type_str.capitalize())
    content_type = ContentType.objects.get_for_model(model)
    obj = model.objects.get(id=object_id)

    return TemplateResponse(
        request,
        "lab/note.html#form",
        {
            "object": obj,
            "content_type": content_type_str,
            "form": NoteForm(),
        },
    )


@login_required
def note_delete(request, pk):
    if request.method == "DELETE":
        note = get_object_or_404(Note, id=pk)

        # Get the object and content type before deleting the note
        obj = note.content_object
        content_type_str = note.content_type.model
        object_id = note.object_id

        # Only allow the note creator or staff to delete
        if request.user == note.user or request.user.is_staff:
            note.delete()

            response = render(
                request,
                "lab/note.html#list",
                {
                    "object": obj,
                    "content_type": content_type_str,
                    "user": request.user,
                },
            )
            response["HX-Trigger"] = f"noteCountUpdate-{content_type_str}-{object_id}"
            return response

        return HttpResponseForbidden()


@login_required
def note_count(request):
    if request.method == "GET":
        object_id = request.GET.get("object_id")
        content_type_str = request.GET.get("content_type")

        # Get the content type and object
        model = apps.get_model("lab", content_type_str.capitalize())
        obj = model.objects.get(id=object_id)

        return render(
            request,
            "lab/note.html#summary",
            context={
                "object": obj,
                "content_type": content_type_str,
            },
        )


@login_required
def note_list(request):
    if request.method == "POST":
        object_id = request.POST.get("object_id")
        content_type_str = request.POST.get("content_type")

        # Get the content type and object
        model = apps.get_model("lab", content_type_str.capitalize())
        obj = model.objects.get(id=object_id)

        return render(
            request,
            "lab/note.html#list",
            context={
                "object": obj,
                "content_type": content_type_str,
                "user": request.user,
            },
        )


@login_required
def check_notifications(request):
    """Check if the current user has any unread notifications"""
    try:
        from notifications.models import Notification
        unread_count = Notification.objects.filter(
            recipient=request.user,
            unread=True
        ).count()
        return JsonResponse({
            'has_unread': unread_count > 0,
            'unread_count': unread_count
        })
    except ImportError:
        # If notifications app is not available, return no unread notifications
        return JsonResponse({
            'has_unread': False,
            'unread_count': 0
        })


@login_required
def notifications_page(request):
    """Display notifications page"""
    try:
        from notifications.models import Notification
        notifications = Notification.objects.filter(
            recipient=request.user
        ).order_by('-timestamp')
        
        # Mark notifications as read when viewed
        unread_notifications = notifications.filter(unread=True)
        unread_notifications.update(unread=False)
        
        context = {
            'notifications': notifications,
            'unread_count': unread_notifications.count()
        }
    except ImportError:
        context = {
            'notifications': [],
            'unread_count': 0
        }
    
    # Handle HTMX requests for partial rendering
    if request.headers.get("HX-Request"):
        return render(request, "lab/notifications.html#notifications-content", context)
    
    return render(request, "lab/notifications.html", context)


@login_required
def individual_timeline(request, pk):
    from lab.visualization.timeline import timeline
    return timeline(request, pk)

@login_required
def plots_page(request):
    """View for the plots page showing various data visualizations."""
    from .visualization.plots import plots_page as plots_view
    return plots_view(request)


@login_required
def nl_search(request):
    """
    Natural language search view that converts user queries to SQL and returns results.
    """
    if request.method == "POST":
        query = request.POST.get("query", "").strip()
        
        if not query:
            return render(request, "lab/nl_search.html#nl-search-error", {
                "error": "No query provided."
            })
        
        try:
            # Process the natural language query using Mistral
            result = query_natural_language(query, "mistral")
            
            if result["success"]:
                return render(request, "lab/nl_search.html#nl-search-result", {
                    "query": result["query"],
                    "sql": result["sql"],
                    "result": result["result"],
                    "success": True
                })
            else:
                return render(request, "lab/nl_search.html#nl-search-error", {
                    "error": result["error"]
                })
                
        except Exception as e:
            return render(request, "lab/nl_search.html#nl-search-error", {
                "error": f"An error occurred: {str(e)}"
            })
    
    # GET request - show the search form
    return render(request, "lab/nl_search.html")


@login_required
def generic_create(request):
    """
    Generic view for creating objects of any model type.
    """
    if request.method == "POST":
        model_name = request.POST.get("model_name")
        app_label = request.POST.get("app_label", "lab")
        
        if not model_name:
            return HttpResponseBadRequest("Model name not specified.")
        
        # Get the model class
        try:
            model_class = apps.get_model(app_label=app_label, model_name=model_name)
        except LookupError:
            return HttpResponseBadRequest(f"Model {model_name} not found.")
        
        # Get the appropriate form
        from .forms import FORMS_MAPPING
        form_class = FORMS_MAPPING.get(model_name)
        if not form_class:
            return HttpResponseBadRequest(f"No form available for {model_name}.")
        
        form = form_class(request.POST)
        if form.is_valid():
            # Set created_by field if it exists
            obj = form.save(commit=False)
            if hasattr(obj, 'created_by') and not getattr(obj, 'created_by_id', None):
                obj.created_by = request.user
            # Default status: prefer model-specific, else any status
            if hasattr(obj, 'status') and not getattr(obj, 'status_id', None):
                model_ct = None
                try:
                    model_ct = ContentType.objects.get_for_model(model_class)
                except Exception:
                    model_ct = None
                default_status = None
                if model_ct:
                    default_status = Status.objects.filter(content_type=model_ct).first()
                if not default_status:
                    default_status = Status.objects.first()
                if default_status:
                    obj.status = default_status
            obj.save()
            form.save_m2m()  # Save many-to-many relationships
            
            # Return success response for HTMX
            if request.htmx:
                return render(request, "lab/index.html#create-success", {
                    "object": obj,
                    "model_name": model_name,
                    "app_label": app_label,
                })
            else:
                return redirect('lab:generic_detail', 
                              app_label=app_label, 
                              model_name=model_name, 
                              pk=obj.pk)
        else:
            # Form validation failed
            if request.htmx:
                return render(request, "lab/index.html#create-form", {
                    "form": form,
                    "model_name": model_name,
                    "app_label": app_label,
                })
            else:
                return render(request, "lab/index.html", {
                    "create_form": form,
                    "model_name": model_name,
                    "app_label": app_label,
                })
    
    # GET request - show the form
    model_name = request.GET.get("model_name")
    app_label = request.GET.get("app_label", "lab")
    
    if not model_name:
        return HttpResponseBadRequest("Model name not specified.")
    
    # Get the model class
    try:
        model_class = apps.get_model(app_label=app_label, model_name=model_name)
    except LookupError:
        return HttpResponseBadRequest(f"Model {model_name} not found.")
    
    # Get the appropriate form
    from .forms import FORMS_MAPPING
    form_class = FORMS_MAPPING.get(model_name)
    if not form_class:
        return HttpResponseBadRequest(f"No form available for {model_name}.")
    
    form = form_class()
    
    if request.htmx:
        return render(request, "lab/index.html#create-form", {
            "form": form,
            "model_name": model_name,
            "app_label": app_label,
        })
    else:
        return render(request, "lab/index.html", {
            "create_form": form,
            "model_name": model_name,
            "app_label": app_label,
        })


@login_required
def generic_edit(request):
    """
    Generic view for editing objects of any model type.
    """
    if request.method == "POST":
        model_name = request.POST.get("model_name")
        app_label = request.POST.get("app_label", "lab")
        pk = request.POST.get("pk")
        
        if not all([model_name, pk]):
            return HttpResponseBadRequest("Model name and pk not specified.")
        
        # Get the model class
        try:
            model_class = apps.get_model(app_label=app_label, model_name=model_name)
        except LookupError:
            return HttpResponseBadRequest(f"Model {model_name} not found.")
        
        # Get the object
        obj = get_object_or_404(model_class, pk=pk)
        
        # Get the appropriate form
        from .forms import FORMS_MAPPING
        form_class = FORMS_MAPPING.get(model_name)
        if not form_class:
            return HttpResponseBadRequest(f"No form available for {model_name}.")
        
        form = form_class(request.POST, instance=obj)
        if form.is_valid():
            # Set updated_at field if it exists
            obj = form.save(commit=False)
            if hasattr(obj, 'updated_at'):
                obj.updated_at = timezone.now()
            obj.save()
            form.save_m2m()  # Save many-to-many relationships
            
            # Return success response for HTMX
            if request.htmx:
                return render(request, "lab/index.html#edit-success", {
                    "object": obj,
                    "model_name": model_name,
                    "app_label": app_label,
                })
            else:
                return redirect('lab:generic_detail', 
                              app_label=app_label, 
                              model_name=model_name, 
                              pk=obj.pk)
        else:
            # Form validation failed
            if request.htmx:
                return render(request, "lab/index.html#edit-form", {
                    "form": form,
                    "object": obj,
                    "model_name": model_name,
                    "app_label": app_label,
                })
            else:
                return render(request, "lab/index.html", {
                    "edit_form": form,
                    "object": obj,
                    "model_name": model_name,
                    "app_label": app_label,
                })
    
    # GET request - show the form
    model_name = request.GET.get("model_name")
    app_label = request.GET.get("app_label", "lab")
    pk = request.GET.get("pk")
    
    if not all([model_name, pk]):
        return HttpResponseBadRequest("Model name and pk not specified.")
    
    # Get the model class
    try:
        model_class = apps.get_model(app_label=app_label, model_name=model_name)
    except LookupError:
        return HttpResponseBadRequest(f"Model {model_name} not found.")
    
    # Get the object
    obj = get_object_or_404(model_class, pk=pk)
    
    # Get the appropriate form
    from .forms import FORMS_MAPPING
    form_class = FORMS_MAPPING.get(model_name)
    if not form_class:
        return HttpResponseBadRequest(f"No form available for {model_name}.")
    
    form = form_class(instance=obj)
    
    if request.htmx:
        return render(request, "lab/index.html#edit-form", {
            "form": form,
            "object": obj,
            "model_name": model_name,
            "app_label": app_label,
        })
    else:
        return render(request, "lab/index.html", {
            "edit_form": form,
            "object": obj,
            "model_name": model_name,
            "app_label": app_label,
        })


@login_required
def generic_delete(request):
    """
    Generic view for deleting objects of any model type.
    """
    if request.method == "POST":
        model_name = request.POST.get("model_name")
        app_label = request.POST.get("app_label", "lab")
        pk = request.POST.get("pk")
        
        if not all([model_name, pk]):
            return HttpResponseBadRequest("Model name and pk not specified.")
        
        # Get the model class
        try:
            model_class = apps.get_model(app_label=app_label, model_name=model_name)
        except LookupError:
            return HttpResponseBadRequest(f"Model {model_name} not found.")
        
        # Get the object
        obj = get_object_or_404(model_class, pk=pk)
        
        # Store info before deletion for response
        object_name = str(obj)
        
        # Delete the object
        obj.delete()
        
        # Return success response for HTMX
        if request.htmx:
            return render(request, "lab/index.html#delete-success", {
                "model_name": model_name,
                "app_label": app_label,
                "object_name": object_name,
            })
        else:
            # Redirect to index or search page
            return redirect('lab:index')
    
    # GET request - show confirmation
    model_name = request.GET.get("model_name")
    app_label = request.GET.get("app_label", "lab")
    pk = request.GET.get("pk")
    
    if not all([model_name, pk]):
        return HttpResponseBadRequest("Model name and pk not specified.")
    
    # Get the model class
    try:
        model_class = apps.get_model(app_label=app_label, model_name=model_name)
    except LookupError:
        return HttpResponseBadRequest(f"Model {model_name} not found.")
    
    # Get the object
    obj = get_object_or_404(model_class, pk=pk)
    
    if request.htmx:
        return render(request, "lab/index.html#delete-confirm", {
            "object": obj,
            "model_name": model_name,
            "app_label": app_label,
        })
    else:
        return render(request, "lab/index.html", {
            "delete_confirm": obj,
            "model_name": model_name,
            "app_label": app_label,
        })


@login_required
def nl_search_page(request):
    """
    Standalone page for natural language search.
    """
    if request.headers.get("HX-Request"):
        # Return just the main content for HTMX insertion
        return render(request, "lab/nl_search.html#nl-search-content", {})
    else:
        # Return the main index page with the nl-search content injected
        from django.template.loader import render_to_string
        
        # Render the nl-search content
        nl_search_html = render_to_string("lab/nl_search.html#nl-search-content", {}, request=request)
        
        # Return the main index page with the nl-search content injected
        return render(request, "lab/index.html", {"initial_nl_search_html": nl_search_html})
