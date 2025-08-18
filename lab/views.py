from django.apps import apps
from django.shortcuts import render, redirect
from django.urls import reverse
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
from django.template import TemplateDoesNotExist
from django.template.response import TemplateResponse

# Import models
from .models import (
    Individual,
    Test,
    Analysis,
    Sample,
    Task,
    Note,
    Institution,
    IdentifierType,
    CrossIdentifier,
    Family,
)

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
@require_POST
def task_complete(request, pk):
    """Mark a Task as completed and return the updated card/detail partial.

    Uses the Task.complete(user) model method to set status to 'Completed'.
    """
    task = get_object_or_404(Task, pk=pk)
    try:
        was_changed = task.complete(request.user)
    except Exception as e:
        return HttpResponseBadRequest(str(e))

    # Decide which partial to render based on provided context
    # Prefer to update the card in lists; fall back to detail when needed
    template_name = "lab/task.html#card"
    if request.POST.get("view") == "detail":
        template_name = "lab/task.html#detail"

    response = render(
        request,
        template_name,
        {
            "item": task,
            "model_name": "Task",
            "app_label": "lab",
        },
    )
    # Optionally trigger a front-end event to refresh filters/counts
    response["HX-Trigger"] = json.dumps({
        "taskStatusUpdated": {"pk": task.pk, "status": getattr(task.status, "name", None)},
        "filters-updated": True,
    })
    return response


@login_required
@require_POST
def task_reopen(request, pk):
    """Reopen a Task by setting its status to 'Active' and return updated partial."""
    task = get_object_or_404(Task, pk=pk)
    # Find an 'Active' status (case-insensitive)
    active_status = Status.objects.filter(name__iexact="active").first()
    if not active_status:
        return HttpResponseBadRequest("No 'Active' status found in Status model.")
    # Update if different
    if task.status_id != active_status.id:
        task.status = active_status
        # Update related object's status if supported
        if hasattr(task.content_object, "update_status"):
            task.content_object.update_status(
                active_status,
                request.user,
                f"Status updated via task reopen: {task.title}",
            )
        task.save()

    template_name = "lab/task.html#card"
    if request.POST.get("view") == "detail":
        template_name = "lab/task.html#detail"

    response = render(
        request,
        template_name,
        {
            "item": task,
            "model_name": "Task",
            "app_label": "lab",
        },
    )
    response["HX-Trigger"] = json.dumps({
        "taskStatusUpdated": {"pk": task.pk, "status": getattr(task.status, "name", None)},
        "filters-updated": True,
    })
    return response


@login_required
def index(request):
    context = {
        "institutions": Institution.objects.all(),
        "individual_statuses": Status.objects.filter(
            Q(content_type=ContentType.objects.get_for_model(Individual)) | 
            Q(content_type__isnull=True)
        ).order_by('name')
    }
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
    # Combobox render mode (for Select2-like behavior)
    render_mode = request.GET.get("render")
    if render_mode == "combobox":
        # Exclude already selected ids
        exclude_ids_raw = request.GET.get("exclude_ids", "")
        exclude_ids = []
        if exclude_ids_raw:
            try:
                exclude_ids = json.loads(exclude_ids_raw)
            except Exception:
                try:
                    exclude_ids = [int(x) for x in exclude_ids_raw.split(",") if x.strip()]
                except Exception:
                    exclude_ids = []

        if exclude_ids:
            try:
                paged_items.object_list = paged_items.object_list.exclude(pk__in=exclude_ids)
                # Recreate paginator for accurate counts if exclusion affected page
                paginator = Paginator(paged_items.object_list, 12)
                paged_items = paginator.get_page(page)
            except Exception:
                pass

        value_field = request.GET.get("value_field", "pk")
        label_field = request.GET.get("label_field")

        # Build option dicts for template rendering
        options = []
        try:
            for obj in paged_items.object_list:
                try:
                    value = getattr(obj, value_field) if value_field and value_field != "pk" else getattr(obj, "pk")
                except Exception:
                    value = getattr(obj, "pk")
                try:
                    label = getattr(obj, label_field) if label_field else str(obj)
                except Exception:
                    label = str(obj)
                options.append({"value": value, "label": str(label)})
        except Exception:
            # Fallback: simple string labels
            options = [{"value": getattr(obj, "pk"), "label": str(obj)} for obj in paged_items.object_list]

        context = {
            "items": paged_items,
            "app_label": target_app_label,
            "model_name": target_model_name,
            "value_field": value_field,
            "label_field": label_field,
            "options": options,
        }
        # Try model-specific combobox-options partial first, fall back to generic
        try:
            return render(request, f"lab/{target_model_name.lower()}.html#combobox-options", context)
        except TemplateDoesNotExist:
            return render(request, "lab/index.html#combobox-options", context)

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
    # Combobox render mode (for Select2-like behavior)
    render_mode = request.GET.get("render")
    if render_mode == "combobox":
        # Exclude already selected ids
        exclude_ids_raw = request.GET.get("exclude_ids", "")
        exclude_ids = []
        if exclude_ids_raw:
            try:
                exclude_ids = json.loads(exclude_ids_raw)
            except Exception:
                try:
                    exclude_ids = [int(x) for x in exclude_ids_raw.split(",") if x.strip()]
                except Exception:
                    exclude_ids = []

        if exclude_ids:
            try:
                paged_items.object_list = paged_items.object_list.exclude(pk__in=exclude_ids)
                paginator = Paginator(paged_items.object_list, 12)
                paged_items = paginator.get_page(page)
            except Exception:
                pass

        value_field = request.GET.get("value_field", "pk")
        label_field = request.GET.get("label_field")

        # Build option dicts for template rendering
        options = []
        try:
            for obj in paged_items.object_list:
                try:
                    value = getattr(obj, value_field) if value_field and value_field != "pk" else getattr(obj, "pk")
                except Exception:
                    value = getattr(obj, "pk")
                try:
                    label = getattr(obj, label_field) if label_field else str(obj)
                except Exception:
                    label = str(obj)
                options.append({"value": value, "label": str(label)})
        except Exception:
            # Fallback: simple string labels
            options = [{"value": getattr(obj, "pk"), "label": str(obj)} for obj in paged_items.object_list]

        context = {
            "items": paged_items,
            "model_name": target_model_name,
            "app_label": target_app_label,
            "value_field": value_field,
            "label_field": label_field,
            "options": options,
        }
        try:
            return render(request, f"lab/{target_model_name.lower()}.html#combobox-options", context)
        except TemplateDoesNotExist:
            return render(request, "lab/index.html#combobox-options", context)

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
def note_update(request, pk):
    """Update an existing note"""
    if request.method == "POST":
        note = get_object_or_404(Note, id=pk)
        
        # Only allow the note creator or staff to edit
        if request.user == note.user or request.user.is_staff:
            note.content = request.POST.get("content")
            note.save()
            
            # Get the object and content type for the response
            obj = note.content_object
            content_type_str = note.content_type.model
            object_id = note.object_id
            
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
            # Save the object with the user context for created_by field
            obj = form.save(user=request.user)
            # Generic: handle any ManyToMany fields posted as JSON lists via <field_name>_ids
            try:
                for m2m_field in obj._meta.many_to_many:
                    field_name = m2m_field.name
                    candidate_params = [f"{field_name}_ids"]
                    if field_name.endswith('s'):
                        candidate_params.append(f"{field_name[:-1]}_ids")
                    json_val = None
                    for pname in candidate_params:
                        json_val = request.POST.get(pname)
                        if json_val:
                            break
                    if not json_val:
                        continue
                    try:
                        id_list = json.loads(json_val)
                    except Exception:
                        id_list = [v for v in (json_val or '').split(',') if v]
                    if isinstance(id_list, list) and id_list:
                        related_model = m2m_field.remote_field.model
                        related_qs = related_model.objects.filter(pk__in=id_list)
                        getattr(obj, field_name).set(related_qs)
            except Exception:
                pass
            
            # Default status: prefer model-specific, else any status
            if hasattr(obj, 'status') and not getattr(obj, 'status_id', None):
                model_ct = None
                try:
                    model_ct = ContentType.objects.get_for_model(model_class)
                    # Try to get a model-specific status first
                    default_status = Status.objects.filter(content_type=model_ct).first()
                    # If no model-specific status, fall back to any status
                    if not default_status:
                        default_status = Status.objects.first()
                except Exception:
                    # Fallback to any status if there's an error
                    default_status = Status.objects.first()
                
                if default_status:
                    obj.status = default_status
                    obj.save()
            
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
    
    # Build initial data from query parameters when possible (e.g., preselect individual on Sample creation)
    initial_data = {}
    try:
        candidate_fields = form_class().fields
        for key, value in request.GET.items():
            if key in candidate_fields:
                initial_data[key] = value
    except Exception:
        initial_data = {}

    form = form_class(initial=initial_data)
    
    # Filter status field to only show statuses for this model class
    if hasattr(form, 'fields') and 'status' in form.fields:
        try:
            model_ct = ContentType.objects.get_for_model(model_class)
            # Filter statuses to only show those for this model type
            filtered_statuses = Status.objects.filter(
                Q(content_type=model_ct) | Q(content_type__isnull=True)
            ).order_by('name')
            form.fields['status'].queryset = filtered_statuses
            print(f"DEBUG: Filtered statuses for {model_name}: {filtered_statuses.count()} statuses found")
            print(f"DEBUG: Model CT: {model_ct}")
            print(f"DEBUG: Available statuses: {[s.name for s in filtered_statuses]}")
        except Exception as e:
            print(f"Error filtering statuses for {model_name}: {e}")
            # Fallback to all statuses if filtering fails
            form.fields['status'].queryset = Status.objects.all().order_by('name')
    
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
            # Save the object with updated_at handled by the form
            obj = form.save()
            
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
    
    # Filter status field to only show statuses for this model class
    if hasattr(form, 'fields') and 'status' in form.fields:
        try:
            model_ct = ContentType.objects.get_for_model(model_class)
            # Filter statuses to only show those for this model type
            filtered_statuses = Status.objects.filter(
                Q(content_type=model_ct) | Q(content_type__isnull=True)
            ).order_by('name')
            form.fields['status'].queryset = filtered_statuses
            print(f"DEBUG: Filtered statuses for {model_name}: {filtered_statuses.count()} statuses found")
            print(f"DEBUG: Model CT: {model_ct}")
            print(f"DEBUG: Available statuses: {[s.name for s in filtered_statuses]}")
        except Exception as e:
            print(f"Error filtering statuses for {model_name}: {e}")
            # Fallback to all statuses if filtering fails
            form.fields['status'].queryset = Status.objects.all().order_by('name')
    
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





@login_required
def family_create_segway(request):
    """
    Segway view that handles family creation with multiple individuals.
    Parses the form data and calls generic_create for the family and individuals.
    """
    if request.method == "POST":
        try:
            # Debug: Print all POST data
            print("=== DEBUG: All POST data ===")
            for key, value in request.POST.items():
                print(f"{key}: {value}")
            print("=== END POST data ===")
            
            # Extract family data
            family_id = request.POST.get('family_id')
            family_description = request.POST.get('family_description', '')
            
            print(f"=== DEBUG: Received family_id: '{family_id}' ===")
            print(f"=== DEBUG: Received family_description: '{family_description}' ===")
            
            if not family_id:
                return HttpResponseBadRequest("Family ID is required.")
            
            # Check if family already exists
            existing_family = None
            try:
                existing_family = Family.objects.get(family_id=family_id)
                print(f"=== DEBUG: Family with ID '{family_id}' already exists ===")
            except Family.DoesNotExist:
                print(f"=== DEBUG: Family with ID '{family_id}' does not exist, will create new ===")
            
            # If family exists, use it; otherwise create new one
            if existing_family:
                family = existing_family
                family_was_created = False
                print(f"=== DEBUG: Using existing family with ID: {family.id} ===")
            else:
                # Create new family directly without form validation
                # This bypasses the ChoiceField validation issue
                try:
                    family = Family.objects.create(
                        family_id=family_id,
                        description=family_description,
                        created_by=request.user
                    )
                    family_was_created = True
                    print(f"=== DEBUG: Family created with ID: {family.id} ===")
                except Exception as e:
                    error_msg = f"Error creating family: {str(e)}"
                    print(f"=== DEBUG: {error_msg} ===")
                    if request.htmx:
                        return render(
                            request,
                            "lab/individual.html#family-create-error",
                            {
                                "error": error_msg,
                            },
                        )
                    else:
                        return HttpResponseBadRequest(error_msg)
            
            # Extract individual data
            individuals_data = {}
            for key, value in request.POST.items():
                if key.startswith('individuals[') and ']' in key:
                    # Parse key like "individuals[0][full_name]" -> index=0, field=full_name
                    parts = key.split('[')
                    if len(parts) == 3:
                        index = parts[1].rstrip(']')
                        field = parts[2].rstrip(']')
                        
                        if index not in individuals_data:
                            individuals_data[index] = {}
                        individuals_data[index][field] = value
            
            print(f"=== DEBUG: Extracted individuals data: {individuals_data} ===")
            
            created_individuals = []  # list of tuples: (index, individual)
            mother_individual = None
            father_individual = None
            
            # First pass: create all individuals
            # Pre-compute a default status for Individuals if not provided
            try:
                indiv_ct = ContentType.objects.get_for_model(Individual)
                default_individual_status = (
                    Status.objects.filter(Q(content_type=indiv_ct) | Q(content_type__isnull=True))
                    .order_by('name')
                    .first()
                )
                print(f"=== DEBUG: Default individual status: {default_individual_status} ===")
            except Exception as e:
                print(f"=== DEBUG: Error getting default status: {e} ===")
                default_individual_status = None

            for index, individual_data in individuals_data.items():
                print(f"=== DEBUG: Processing individual {index}: {individual_data} ===")
                # Only require full_name, role and minimal fields; id is optional (auto field)
                if not individual_data.get('full_name'):
                    print(f"=== DEBUG: Skipping individual {index} - no full_name ===")
                    continue
                
                if not individual_data.get('role'):
                    print(f"=== DEBUG: Skipping individual {index} - no role ===")
                    continue
                
                # Get required fields
                individual_form_data = {
                    # If explicit id is provided, pass it through; otherwise omit
                    'id': individual_data.get('id'),
                    'full_name': individual_data.get('full_name'),
                    'tc_identity': individual_data.get('tc_identity') or None,
                    'birth_date': individual_data.get('birth_date') or None,
                    'icd11_code': individual_data.get('icd11_code') or None,
                    'council_date': individual_data.get('council_date') or None,
                    'diagnosis': individual_data.get('diagnosis') or None,
                    'diagnosis_date': individual_data.get('diagnosis_date') or None,
                    'institution': individual_data.get('institution'),
                    'status': individual_data.get('status'),
                    'family': family.id,
                    'is_index': individual_data.get('is_index') == 'true',
                    'is_affected': individual_data.get('is_affected') == 'true',
                }
                
                print(f"=== DEBUG: Individual form data for {index}: {individual_form_data} ===")
                
                # Create the individual
                from .forms import IndividualForm
                # Remove id if blank to avoid validation errors
                if not individual_form_data.get('id'):
                    individual_form_data.pop('id', None)

                # If status not provided, inject a default one
                if not individual_form_data.get('status') and default_individual_status:
                    individual_form_data['status'] = default_individual_status.id
                    print(f"=== DEBUG: Added default status {default_individual_status.id} for individual {index} ===")

                individual_form = IndividualForm(individual_form_data)
                print(f"=== DEBUG: Individual form is_valid: {individual_form.is_valid()} ===")
                if individual_form.is_valid():
                    individual = individual_form.save(commit=False)
                    individual.created_by = request.user
                    individual.save()
                    individual_form.save_m2m()
                    
                    print(f"=== DEBUG: Individual {index} created successfully with ID: {individual.id} ===")
                    created_individuals.append((index, individual))
                    
                    # Store mother and father for later reference
                    role = individual_data.get('role', '')
                    if role == 'mother':
                        mother_individual = individual
                        print(f"=== DEBUG: Individual {index} marked as mother ===")
                    elif role == 'father':
                        father_individual = individual
                        print(f"=== DEBUG: Individual {index} marked as father ===")
                else:
                    print(f"=== DEBUG: Individual form validation failed for {index}: {individual_form.errors} ===")
            
            print(f"=== DEBUG: Total individuals created: {len(created_individuals)} ===")
            
            # Validate that we have at least one mother and one father if there are multiple individuals
            if len(created_individuals) > 1:
                has_mother = any(individuals_data.get(idx, {}).get('role') == 'mother' for idx, _ in created_individuals)
                has_father = any(individuals_data.get(idx, {}).get('role') == 'father' for idx, _ in created_individuals)
                
                if not has_mother or not has_father:
                    error_msg = "For families with multiple members, at least one mother and one father must be specified."
                    print(f"=== DEBUG: Validation error: {error_msg} ===")
                    if request.htmx:
                        return render(request, "lab/individual.html#family-create-error", {
                            "error": error_msg
                        })
                    else:
                        return HttpResponseBadRequest(error_msg)
            
            # Second pass: update mother/father relationships based on role and create cross identifiers
            for idx, individual in created_individuals:
                # Find the corresponding individual data directly by index
                individual_data = individuals_data.get(idx, {})
                
                if individual_data:
                    # Automatically set mother/father relationships based on role in family
                    role = individual_data.get('role', '')
                    
                    # For siblings and probands, set mother and father if they exist
                    if role in ['sibling', 'proband', 'other']:
                        if mother_individual:
                            individual.mother = mother_individual
                            print(f"=== DEBUG: Set mother for {role} individual {idx} ===")
                        if father_individual:
                            individual.father = father_individual
                            print(f"=== DEBUG: Set father for {role} individual {idx} ===")
                    
                    # For mother, set as mother for all other individuals
                    elif role == 'mother':
                        mother_individual = individual
                        print(f"=== DEBUG: Individual {idx} is mother ===")
                    
                    # For father, set as father for all other individuals
                    elif role == 'father':
                        father_individual = individual
                        print(f"=== DEBUG: Individual {idx} is father ===")
                
                individual.save()

                # Create CrossIdentifier rows for this individual
                try:
                    idx_prefix = f"individuals[{idx}]"
                    # discover all rows present for this individual's ids
                    rows = set()
                    for key in request.POST.keys():
                        if key.startswith(f"{idx_prefix}[ids][") and key.endswith("][value]"):
                            try:
                                after_ids = key.split("[ids][", 1)[1]
                                row_str = after_ids.split("]", 1)[0]
                                rows.add(row_str)
                            except Exception:
                                continue
                    for row in rows:
                        value_key = f"{idx_prefix}[ids][{row}][value]"
                        value = request.POST.get(value_key, "").strip()
                        type_key = f"{idx_prefix}[ids][{row}][type]"
                        type_id = request.POST.get(type_key, "").strip()
                        if value and type_id:
                            try:
                                CrossIdentifier.objects.create(
                                    individual=individual,
                                    id_type_id=int(type_id),
                                    id_value=value,
                                    created_by=request.user,
                                )
                                print(f"=== DEBUG: Created CrossIdentifier for individual {idx}: {type_id}={value} ===")
                            except Exception as e:
                                print(f"=== DEBUG: Error creating CrossIdentifier for individual {idx}: {e} ===")
                                # Ignore malformed IDs silently for now
                                pass
                except Exception as e:
                    print(f"=== DEBUG: Error processing IDs for individual {idx}: {e} ===")
                    # If parsing fails, skip creating IDs for this individual
                    pass

                # Create Note rows for this individual
                try:
                    idx_prefix = f"individuals[{idx}]"
                    print(f"=== DEBUG: Processing notes for individual {idx} with prefix: {idx_prefix} ===")
                    
                    # discover all rows present for this individual's notes
                    note_rows = set()
                    print(f"=== DEBUG: All POST keys for notes processing: ===")
                    for key in request.POST.keys():
                        if key.startswith(f"{idx_prefix}[notes][") and key.endswith("][content]"):
                            print(f"  Found note key: {key}")
                            try:
                                after_notes = key.split("[notes][", 1)[1]
                                row_str = after_notes.split("]", 1)[0]
                                note_rows.add(row_str)
                                print(f"  Extracted row: {row_str}")
                            except Exception as e:
                                print(f"  Error parsing key {key}: {e}")
                                continue
                    
                    print(f"=== DEBUG: Total note rows found for individual {idx}: {len(note_rows)} ===")
                    print(f"=== DEBUG: Note rows set: {note_rows} ===")
                    
                    for row in note_rows:
                        content_key = f"{idx_prefix}[notes][{row}][content]"
                        content = request.POST.get(content_key, "").strip()
                        print(f"=== DEBUG: Processing note row {row}: ===")
                        print(f"  Content key: {content_key}")
                        print(f"  Raw content: '{content}'")
                        print(f"  Content length: {len(content)}")
                        print(f"  Content trimmed: '{content.strip()}'")
                        
                        if content:
                            try:
                                print(f"=== DEBUG: Creating Note object for individual {idx}, row {row} ===")
                                print(f"  Content: {content[:100]}...")
                                print(f"  User: {request.user}")
                                print(f"  Content type: {ContentType.objects.get_for_model(Individual)}")
                                print(f"  Object ID: {individual.id}")
                                
                                Note.objects.create(
                                    content=content,
                                    user=request.user,
                                    content_type=ContentType.objects.get_for_model(Individual),
                                    object_id=individual.id,
                                )
                                print(f"=== DEBUG: Successfully created Note for individual {idx}, row {row}: {content[:50]}... ===")
                            except Exception as e:
                                print(f"=== DEBUG: Error creating Note for individual {idx}, row {row}: {e} ===")
                                print(f"  Exception type: {type(e).__name__}")
                                import traceback
                                traceback.print_exc()
                                # Ignore malformed notes silently for now
                                pass
                        else:
                            print(f"=== DEBUG: Skipping empty note for individual {idx}, row {row} ===")
                except Exception as e:
                    print(f"=== DEBUG: Error processing notes for individual {idx}: {e} ===")
                    print(f"  Exception type: {type(e).__name__}")
                    import traceback
                    traceback.print_exc()
                    # If parsing fails, skip creating notes for this individual
                    pass

                # Generic: attach any ManyToMany posted as JSON lists per-individual
                try:
                    idx_prefix = f"individuals[{idx}]"
                    for m2m_field in individual._meta.many_to_many:
                        field_name = m2m_field.name
                        candidate_params = [f"{idx_prefix}[{field_name}_ids]"]
                        if field_name.endswith('s'):
                            candidate_params.append(f"{idx_prefix}[{field_name[:-1]}_ids]")
                        json_val = None
                        for pname in candidate_params:
                            json_val = request.POST.get(pname)
                            if json_val:
                                break
                        if not json_val:
                            continue
                        try:
                            id_list = json.loads(json_val)
                        except Exception:
                            id_list = [v for v in (json_val or '').split(',') if v]
                        if isinstance(id_list, list) and id_list:
                            related_model = m2m_field.remote_field.model
                            related_qs = related_model.objects.filter(pk__in=id_list)
                            getattr(individual, field_name).set(related_qs)
                except Exception:
                    pass
            
            # Return success response
            if request.htmx:
                return render(
                    request,
                    "lab/individual.html#family-create-success",
                    {
                        "family": family,
                        "individuals": [ind for _, ind in created_individuals],
                        "count": len(created_individuals),
                        "family_was_created": family_was_created,
                    },
                )
            else:
                # Redirect to the family detail page
                return redirect(f"/detail/?app_label=lab&model_name=Family&pk={family.pk}")
                
        except Exception as e:
            print(f"Error in family_create_segway: {e}")
            import traceback
            traceback.print_exc()
            if request.htmx:
                return render(request, "lab/individual.html#family-create-error", {
                    "error": str(e)
                })
            else:
                return HttpResponseBadRequest(f"Error creating family: {str(e)}")
    
    # GET request - show the form
    if request.htmx:
        return render(request, "lab/individual.html#family-create-form", {
            "institutions": Institution.objects.all(),
            "individual_statuses": Status.objects.filter(
                Q(content_type=ContentType.objects.get_for_model(Individual)) | 
                Q(content_type__isnull=True)
            ).order_by('name'),
            "identifier_types": IdentifierType.objects.all().order_by('name'),
            "existing_families": Family.objects.all().order_by('family_id'),
        })
    else:
        return redirect('lab:index')
