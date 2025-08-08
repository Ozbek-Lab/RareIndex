from django.apps import apps
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.db.models import Q
from django.contrib.contenttypes.models import ContentType
import json
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from .models import Note, StatusLog

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
    """Generate timeline data for an individual and all related objects"""
    individual = get_object_or_404(Individual, pk=pk)
    
    timeline_events = []
    
    # Get individual history and important dates (excluding creation events)
    for record in individual.history.all():
        if 'created' not in record.get_history_type_display().lower():
            timeline_events.append({
                'date': record.history_date,
                'type': 'individual',
                'action': record.get_history_type_display(),
                'description': f"Individual {record.get_history_type_display().lower()}",
                'user': record.history_user.username if record.history_user else 'System',
                'object_name': 'Individual',
                'object_id': individual.individual_id,
                'details': f"Status: {record.status.name if record.status else 'N/A'}"
            })
    
    # Add individual's important dates
    if individual.council_date:
        timeline_events.append({
            'date': individual.council_date,
            'type': 'individual',
            'action': 'Council Date',
            'description': 'Council Date',
            'user': 'System',
            'object_name': 'Individual',
            'object_id': individual.individual_id,
            'details': f"Council Date: {individual.council_date}"
        })
    
    if individual.diagnosis_date:
        timeline_events.append({
            'date': individual.diagnosis_date,
            'type': 'individual',
            'action': 'Diagnosis Date',
            'description': 'Diagnosis Date',
            'user': 'System',
            'object_name': 'Individual',
            'object_id': individual.individual_id,
            'details': f"Diagnosis Date: {individual.diagnosis_date}"
        })
    
    # Get sample history and important dates
    for sample in individual.samples.all():
        # Add the actual created_at date
        timeline_events.append({
            'date': sample.created_at,
            'type': 'sample',
            'action': 'Created',
            'description': f"Sample {sample.id} created",
            'user': 'System',
            'object_name': 'Sample',
            'object_id': f"Sample {sample.id}",
            'details': f"Type: {sample.sample_type.name}, Created: {sample.created_at.date()}"
        })
        
        for record in sample.history.all():
            if 'created' not in record.get_history_type_display().lower():
                timeline_events.append({
                    'date': record.history_date,
                    'type': 'sample',
                    'action': record.get_history_type_display()+"Sample",
                    'description': f"Sample {record.get_history_type_display().lower()}",
                    'user': record.history_user.username if record.history_user else 'System',
                    'object_name': 'Sample',
                    'object_id': f"Sample {sample.id}",
                    'details': f"Type: {sample.sample_type.name}, Status: {record.status.name if record.status else 'N/A'}"
                })
        
        # Add sample's important dates
        if sample.receipt_date:
            timeline_events.append({
                'date': sample.receipt_date,
                'type': 'sample',
                'action': 'Receipt Date',
                'description': 'Sample Received',
                'user': 'System',
                'object_name': 'Sample',
                'object_id': f"Sample {sample.id}",
                'details': f"Sample Type: {sample.sample_type.name}, Receipt Date: {sample.receipt_date}"
            })
        
        if sample.processing_date:
            timeline_events.append({
                'date': sample.processing_date,
                'type': 'sample',
                'action': 'Processing Date',
                'description': 'Sample Processed',
                'user': 'System',
                'object_name': 'Sample',
                'object_id': f"Sample {sample.id}",
                'details': f"Sample Type: {sample.sample_type.name}, Processing Date: {sample.processing_date}"
            })
    
    # Get test history and important dates
    for sample in individual.samples.all():
        for test in sample.tests.all():
            # Add the actual created_at date
            timeline_events.append({
                'date': test.created_at,
                'type': 'test',
                'action': 'Created',
                'description': f"Test {test.id} created",
                'user': 'System',
                'object_name': 'Test',
                'object_id': f"Test {test.id}",
                'details': f"Type: {test.test_type.name}, Created: {test.created_at.date()}"
            })
            
            for record in test.history.all():
                if 'created' not in record.get_history_type_display().lower():
                    timeline_events.append({
                        'date': record.history_date,
                        'type': 'test',
                        'action': record.get_history_type_display(),
                        'description': f"Test {record.get_history_type_display().lower()}",
                        'user': record.history_user.username if record.history_user else 'System',
                        'object_name': 'Test',
                        'object_id': f"Test {test.id}",
                        'details': f"Type: {test.test_type.name}, Status: {record.status.name if record.status else 'N/A'}"
                    })
            
            # Add test's important dates
            if test.performed_date:
                timeline_events.append({
                    'date': test.performed_date,
                    'type': 'test',
                    'action': 'Performed Date',
                    'description': 'Test Performed',
                    'user': test.performed_by.username if test.performed_by else 'System',
                    'object_name': 'Test',
                    'object_id': f"Test {test.id}",
                    'details': f"Test Type: {test.test_type.name}, Performed Date: {test.performed_date}"
                })
            
            if test.service_send_date:
                timeline_events.append({
                    'date': test.service_send_date,
                    'type': 'test',
                    'action': 'Service Send Date',
                    'description': 'Test Sent to Service',
                    'user': 'System',
                    'object_name': 'Test',
                    'object_id': f"Test {test.id}",
                    'details': f"Test Type: {test.test_type.name}, Service Send Date: {test.service_send_date}"
                })
            
            if test.data_receipt_date:
                timeline_events.append({
                    'date': test.data_receipt_date,
                    'type': 'test',
                    'action': 'Data Receipt Date',
                    'description': 'Test Data Received',
                    'user': 'System',
                    'object_name': 'Test',
                    'object_id': f"Test {test.id}",
                    'details': f"Test Type: {test.test_type.name}, Data Receipt Date: {test.data_receipt_date}"
                })
    
    # Get analysis history and important dates
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                # Add the actual created_at date
                timeline_events.append({
                    'date': analysis.created_at,
                    'type': 'analysis',
                    'action': 'Created',
                    'description': f"Analysis {analysis.id} created",
                    'user': 'System',
                    'object_name': 'Analysis',
                    'object_id': f"Analysis {analysis.id}",
                    'details': f"Type: {analysis.type.name}, Created: {analysis.created_at.date()}"
                })
                
                for record in analysis.history.all():
                    if 'created' not in record.get_history_type_display().lower():
                        timeline_events.append({
                            'date': record.history_date,
                            'type': 'analysis',
                            'action': record.get_history_type_display(),
                            'description': f"Analysis {record.get_history_type_display().lower()}",
                            'user': record.history_user.username if record.history_user else 'System',
                            'object_name': 'Analysis',
                            'object_id': f"Analysis {analysis.id}",
                            'details': f"Type: {analysis.type.name}, Status: {record.status.name if record.status else 'N/A'}"
                        })
                
                # Add analysis's important dates
                if analysis.performed_date:
                    timeline_events.append({
                        'date': analysis.performed_date,
                        'type': 'analysis',
                        'action': 'Performed Date',
                        'description': 'Analysis Performed',
                        'user': analysis.performed_by.username,
                        'object_name': 'Analysis',
                        'object_id': f"Analysis {analysis.id}",
                        'details': f"Analysis Type: {analysis.type.name}, Performed Date: {analysis.performed_date}"
                    })
    
    # Get task history and important dates
    for task in individual.tasks.all():
        # Add the actual created_at date
        timeline_events.append({
            'date': task.created_at,
            'type': 'task',
            'action': 'Created',
            'description': f"Task {task.id} created",
            'user': 'System',
            'object_name': 'Task',
            'object_id': f"Task {task.id}",
            'details': f"Title: {task.title}, Created: {task.created_at.date()}"
        })
        
        for record in task.history.all():
            if 'created' not in record.get_history_type_display().lower():
                timeline_events.append({
                    'date': record.history_date,
                    'type': 'task',
                    'action': record.get_history_type_display(),
                    'description': f"Task {record.get_history_type_display().lower()}",
                    'user': record.history_user.username if record.history_user else 'System',
                    'object_name': 'Task',
                    'object_id': f"Task {task.id}",
                    'details': f"Priority: {record.priority}, Status: {record.status.name if record.status else 'N/A'}"
                })
        
        # Add task's important dates
        if task.due_date:
            timeline_events.append({
                'date': task.due_date,
                'type': 'task',
                'action': 'Due Date',
                'description': 'Task Due Date',
                'user': 'System',
                'object_name': 'Task',
                'object_id': f"Task {task.id}",
                'details': f"Task: {task.title}, Due Date: {task.due_date}, Priority: {task.priority}"
            })
    
    # Get notes (created_at and updated_at dates)
    for note in individual.notes.all():
        timeline_events.append({
            'date': note.created_at,
            'type': 'note',
            'action': 'Created',
            'description': 'Note added',
            'user': note.user.username,
            'object_name': 'Note',
            'object_id': f"Note {note.id}",
            'details': note.content[:100] + '...' if len(note.content) > 100 else note.content
        })
        
        # Add note update if it was modified
        if note.updated_at and note.updated_at != note.created_at:
            timeline_events.append({
                'date': note.updated_at,
                'type': 'note',
                'action': 'Updated',
                'description': 'Note updated',
                'user': note.user.username,
                'object_name': 'Note',
                'object_id': f"Note {note.id}",
                'details': note.content[:100] + '...' if len(note.content) > 100 else note.content
            })
    
    # Get sample tasks and notes
    for sample in individual.samples.all():
        # Sample tasks
        for task in sample.tasks.all():
            timeline_events.append({
                'date': task.created_at,
                'type': 'task',
                'action': 'Created',
                'description': f"Task {task.id} created",
                'user': 'System',
                'object_name': 'Task',
                'object_id': f"Task {task.id}",
                'details': f"Sample: {sample.id}, Title: {task.title}, Created: {task.created_at.date()}"
            })
            
            for record in task.history.all():
                if 'created' not in record.get_history_type_display().lower():
                    timeline_events.append({
                        'date': record.history_date,
                        'type': 'task',
                        'action': record.get_history_type_display(),
                        'description': f"Task {record.get_history_type_display().lower()}",
                        'user': record.history_user.username if record.history_user else 'System',
                        'object_name': 'Task',
                        'object_id': f"Task {task.id}",
                        'details': f"Sample: {sample.id}, Priority: {record.priority}, Status: {record.status.name if record.status else 'N/A'}"
                    })
            
            # Add task's important dates
            if task.due_date:
                timeline_events.append({
                    'date': task.due_date,
                    'type': 'task',
                    'action': 'Due Date',
                    'description': 'Task Due Date',
                    'user': 'System',
                    'object_name': 'Task',
                    'object_id': f"Task {task.id}",
                    'details': f"Sample: {sample.id}, Task: {task.title}, Due Date: {task.due_date}, Priority: {task.priority}"
                })
        
        # Sample notes
        for note in sample.notes.all():
            timeline_events.append({
                'date': note.created_at,
                'type': 'note',
                'action': 'Created',
                'description': 'Note added',
                'user': note.user.username,
                'object_name': 'Note',
                'object_id': f"Note {note.id}",
                'details': f"Sample: {sample.id}, Content: {note.content[:100]}{'...' if len(note.content) > 100 else ''}"
            })
            
            # Add note update if it was modified
            if note.updated_at and note.updated_at != note.created_at:
                    timeline_events.append({
                        'date': note.updated_at,
                        'type': 'note',
                        'action': 'Updated',
                        'description': 'Note updated',
                        'user': note.user.username,
                        'object_name': 'Note',
                        'object_id': f"Note {note.id}",
                        'details': f"Sample: {sample.id}, Content: {note.content[:100]}{'...' if len(note.content) > 100 else ''}"
                    })
    
    # Get test tasks and notes
    for sample in individual.samples.all():
        for test in sample.tests.all():
            # Test tasks
            for task in test.tasks.all():
                timeline_events.append({
                    'date': task.created_at,
                    'type': 'task',
                    'action': 'Created',
                    'description': f"Task {task.id} created",
                    'user': 'System',
                    'object_name': 'Task',
                    'object_id': f"Task {task.id}",
                    'details': f"Test: {test.id}, Title: {task.title}, Created: {task.created_at.date()}"
                })
                
                for record in task.history.all():
                    if 'created' not in record.get_history_type_display().lower():
                        timeline_events.append({
                            'date': record.history_date,
                            'type': 'task',
                            'action': record.get_history_type_display(),
                            'description': f"Task {record.get_history_type_display().lower()}",
                            'user': record.history_user.username if record.history_user else 'System',
                            'object_name': 'Task',
                            'object_id': f"Task {task.id}",
                            'details': f"Test: {test.id}, Priority: {record.priority}, Status: {record.status.name if record.status else 'N/A'}"
                        })
                
                # Add task's important dates
                if task.due_date:
                    timeline_events.append({
                        'date': task.due_date,
                        'type': 'task',
                        'action': 'Due Date',
                        'description': 'Task Due Date',
                        'user': 'System',
                        'object_name': 'Task',
                        'object_id': f"Task {task.id}",
                        'details': f"Test: {test.id}, Task: {task.title}, Due Date: {task.due_date}, Priority: {task.priority}"
                    })
            
            # Test notes
            for note in test.notes.all():
                timeline_events.append({
                    'date': note.created_at,
                    'type': 'note',
                    'action': 'Created',
                    'description': 'Note added',
                    'user': note.user.username,
                    'object_name': 'Note',
                    'object_id': f"Note {note.id}",
                    'details': f"Test: {test.id}, Content: {note.content[:100]}{'...' if len(note.content) > 100 else ''}"
                })
                
                # Add note update if it was modified
                if note.updated_at and note.updated_at != note.created_at:
                    timeline_events.append({
                        'date': note.updated_at,
                        'type': 'note',
                        'action': 'Updated',
                        'description': 'Note updated',
                        'user': note.user.username,
                        'object_name': 'Note',
                        'object_id': f"Note {note.id}",
                        'details': f"Test: {test.id}, Content: {note.content[:100]}{'...' if len(note.content) > 100 else ''}"
                    })
    
    # Get analysis tasks and notes
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                # Analysis tasks
                for task in analysis.tasks.all():
                    timeline_events.append({
                        'date': task.created_at,
                        'type': 'task',
                        'action': 'Created',
                        'description': f"Task {task.id} created",
                        'user': 'System',
                        'object_name': 'Task',
                        'object_id': f"Task {task.id}",
                        'details': f"Analysis: {analysis.id}, Title: {task.title}, Created: {task.created_at.date()}"
                    })
                    
                    for record in task.history.all():
                        if 'created' not in record.get_history_type_display().lower():
                            timeline_events.append({
                                'date': record.history_date,
                                'type': 'task',
                                'action': record.get_history_type_display(),
                                'description': f"Task {record.get_history_type_display().lower()}",
                                'user': record.history_user.username if record.history_user else 'System',
                                'object_name': 'Task',
                                'object_id': f"Task {task.id}",
                                'details': f"Analysis: {analysis.id}, Priority: {record.priority}, Status: {record.status.name if record.status else 'N/A'}"
                            })
                    
                    # Add task's important dates
                    if task.due_date:
                        timeline_events.append({
                            'date': task.due_date,
                            'type': 'task',
                            'action': 'Due Date',
                            'description': 'Task Due Date',
                            'user': 'System',
                            'object_name': 'Task',
                            'object_id': f"Task {task.id}",
                            'details': f"Analysis: {analysis.id}, Task: {task.title}, Due Date: {task.due_date}, Priority: {task.priority}"
                        })
                
                # Analysis notes
                for note in analysis.notes.all():
                    timeline_events.append({
                        'date': note.created_at,
                        'type': 'note',
                        'action': 'Created',
                        'description': 'Note added',
                        'user': note.user.username,
                        'object_name': 'Note',
                        'object_id': f"Note {note.id}",
                        'details': f"Analysis: {analysis.id}, Content: {note.content[:100]}{'...' if len(note.content) > 100 else ''}"
                    })
                    
                    # Add note update if it was modified
                    if note.updated_at and note.updated_at != note.created_at:
                        timeline_events.append({
                            'date': note.updated_at,
                            'type': 'note',
                            'action': 'Updated',
                            'description': 'Note updated',
                            'user': note.user.username,
                            'object_name': 'Note',
                            'object_id': f"Note {note.id}",
                            'details': f"Analysis: {analysis.id}, Content: {note.content[:100]}{'...' if len(note.content) > 100 else ''}"
                        })
    

    
    # Get status log entries
    for status_log in StatusLog.objects.filter(
        content_type=ContentType.objects.get_for_model(Individual),
        object_id=individual.id
    ):
        timeline_events.append({
            'date': status_log.changed_at,
            'type': 'individual',
            'action': 'Status Changed',
            'description': f"Status changed from {status_log.previous_status.name} to {status_log.new_status.name}",
            'user': status_log.changed_by.username,
            'object_name': 'Individual',
            'object_id': individual.individual_id,
            'details': f"Previous: {status_log.previous_status.name}, New: {status_log.new_status.name}, Notes: {status_log.notes}"
        })
    
    # Convert all dates to timezone-aware datetime.datetime objects and sort timeline events by date
    from datetime import datetime, time, date
    from django.utils import timezone
    
    for event in timeline_events:
        if isinstance(event['date'], date) and not isinstance(event['date'], datetime):
            # Convert date to timezone-aware datetime at midnight
            event['date'] = timezone.make_aware(datetime.combine(event['date'], time.min))
        elif isinstance(event['date'], datetime) and timezone.is_naive(event['date']):
            # Convert naive datetime to timezone-aware
            event['date'] = timezone.make_aware(event['date'])
    
    for event in timeline_events:
        if isinstance(event['date'], datetime):
            # Convert datetime to date
            event['date'] = event['date'].date()
    # If it's already a date (but not a datetime), leave as is

    timeline_events.sort(key=lambda x: x['date'], reverse=True)

    # Prepare data for Plotly timeline - use only date objects and assign hierarchical positions
    from django.utils import timezone
    
    # Pre-calculate y-positions using depth-first search
    sample_positions = {}
    test_positions = {}
    analysis_positions = {}
    task_positions = {}
    note_positions = {}
    
    # Configuration
    sample_offset = 1
    test_offset = 0.5
    analysis_offset = 0.25
    
    # Assign y-positions using depth-first search with chronological ordering within each level
    current_y = 0  # Individual is at 0
    
    # Process samples and their children in chronological order
    all_samples = list(individual.samples.all())
    all_samples.sort(key=lambda s: s.created_at.date() if s.created_at else date(2025, 1, 1))
    
    for sample in all_samples:
        # Assign sample position
        sample_positions[sample.id] = current_y + sample_offset
        current_y = sample_positions[sample.id]
        
        # Process tests for this sample in chronological order
        all_tests = list(sample.tests.all())
        all_tests.sort(key=lambda t: t.created_at.date() if t.created_at else date(2025, 1, 1))
        
        for test in all_tests:
            # Assign test position
            test_positions[test.id] = current_y + test_offset
            current_y = test_positions[test.id]
            
            # Process analyses for this test in chronological order
            all_analyses = list(test.analyses.all())
            all_analyses.sort(key=lambda a: a.created_at.date() if a.created_at else date(2025, 1, 1))
            
            for analysis in all_analyses:
                # Assign analysis position
                analysis_positions[analysis.id] = current_y + analysis_offset
                current_y = analysis_positions[analysis.id]
    
    # Process individual tasks and notes in chronological order (mixed together)
    current_y = -0.25  # Start at -0.25 for individual tasks and notes
    
    all_tasks = list(individual.tasks.all())
    all_notes = list(individual.notes.all())
    
    # Combine and sort by creation date
    tasks_and_notes = [(task, 'task') for task in all_tasks] + [(note, 'note') for note in all_notes]
    tasks_and_notes.sort(key=lambda x: x[0].created_at.date() if x[0].created_at else date(2025, 1, 1))
    
    for obj, obj_type in tasks_and_notes:
        if obj_type == 'task':
            task_positions[obj.id] = current_y
            current_y -= 0.25
        elif obj_type == 'note':
            note_positions[obj.id] = current_y
            current_y -= 0.25
    
    # Now process timeline events with pre-assigned positions
    y_positions = []
    dates = []
    descriptions = []
    types = []
    users = []
    details = []
    
    for event in timeline_events:
        # Convert dates to ISO format strings for Plotly (YYYY-MM-DD)
        dates.append(event['date'].isoformat())
        descriptions.append(event['description'])
        types.append(event['type'])
        users.append(event['user'])
        details.append(event['details'])
        
        # Assign y-position based on pre-calculated positions
        if event['type'] == 'individual':
            y_positions.append(0)  # Main timeline
        elif event['type'] == 'sample':
            sample_id = int(event['object_id'].split()[-1] if ' ' in event['object_id'] else event['object_id'])
            y_positions.append(sample_positions.get(sample_id, 0))
        elif event['type'] == 'test':
            test_id = int(event['object_id'].split()[-1] if ' ' in event['object_id'] else event['object_id'])
            y_positions.append(test_positions.get(test_id, 0))
        elif event['type'] == 'analysis':
            analysis_id = int(event['object_id'].split()[-1] if ' ' in event['object_id'] else event['object_id'])
            y_positions.append(analysis_positions.get(analysis_id, 0))
        elif event['type'] == 'task':
            task_id = int(event['object_id'].split()[-1] if ' ' in event['object_id'] else event['object_id'])
            y_positions.append(task_positions.get(task_id, 0))
        elif event['type'] == 'note':
            note_id = int(event['object_id'].split()[-1] if ' ' in event['object_id'] else event['object_id'])
            y_positions.append(note_positions.get(note_id, 0))
        else:
            y_positions.append(0)  # Default to main timeline
    
    
    # Color mapping for different types
    color_map = {
        'individual': '#1f77b4',
        'sample': '#ff7f0e', 
        'test': '#2ca02c',
        'analysis': '#d62728',
        'task': '#9467bd',
        'note': '#8c564b'
    }
    
    # Width mapping for different types
    width_map = {
        'individual': 3,
        'sample': 2, 
        'test': 2,
        'analysis': 2,
        'task': 2,
        'note': 2
    }
    
    colors = [color_map.get(event_type, '#7f7f7f') for event_type in types]
    
    # Create Plotly figure
    import plotly.graph_objects as go
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=dates,
        y=y_positions,  # Use hierarchical y-positions
        mode='markers',
        marker=dict(    
            size=12,
            color=colors,
            symbol='circle'
        ),
        text=descriptions,
        textposition='top center',
        hovertemplate='<b>%{text}</b><br>' +
                     'Date: %{x}<br>' +
                     'Action: %{customdata[2]}<br>' +
                     'User: %{customdata[0]}<br>' +
                     'Details: %{customdata[1]}<br>' +
                     '<extra></extra>',
        customdata=list(zip(users, details, [event['action'] for event in timeline_events])),
        name='Timeline Events'
    ))

    # Add lines connecting events for the same object
    from collections import defaultdict
    object_event_lines = defaultdict(list)
    for i, event in enumerate(timeline_events):
        object_event_lines[event['object_id']].append((dates[i], y_positions[i]))

    for object_id, points in object_event_lines.items():
        if len(points) > 1:
            points.sort()
            x_vals, y_vals = zip(*points)
            # Determine the color based on the object type
            object_type = None
            for event in timeline_events:
                if event['object_id'] == object_id:
                    object_type = event['type']
                    break
            line_color = color_map.get(object_type, '#7f7f7f')
            fig.add_trace(go.Scatter(
                x=x_vals,
                y=y_vals,
                mode='lines',
                line=dict(width=2, color=line_color),
                showlegend=False,
                hoverinfo='skip',
            ))
    
    # Add horizontal lines for each level of the hierarchy with proper branching
    max_y = max(y_positions) if y_positions else 0
    min_y = min(y_positions) if y_positions else 0
    
    # Individual line - from created_at to now
    from datetime import date
    individual_created = individual.created_at.date().isoformat() if individual.created_at else '2025-01-01'
    fig.add_shape(
        type='line',
        x0=individual_created,
        x1=date.today().isoformat(),
        y0=0,
        y1=0,
        line=dict(color=color_map['individual'], width=width_map['individual'])
    )
    
    # Get actual creation dates from models
    sample_creation_dates = {}
    test_creation_dates = {}
    analysis_creation_dates = {}
    
    # Get sample creation dates
    for sample in individual.samples.all():
        sample_creation_dates[sample.id] = sample.created_at.date().isoformat()
    
    # Get test creation dates
    for sample in individual.samples.all():
        for test in sample.tests.all():
            test_creation_dates[test.id] = test.created_at.date().isoformat()
    
    # Get analysis creation dates
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                analysis_creation_dates[analysis.id] = analysis.created_at.date().isoformat()
    

    
    # Sample lines - from created_at to now
    for sample in individual.samples.all():
        if sample.id in sample_positions:
            sample_created = sample.created_at.date().isoformat() if sample.created_at else '2025-01-01'
            fig.add_shape(
                type='line',
                x0=sample_created,
                x1=date.today().isoformat(),
                y0=sample_positions[sample.id],
                y1=sample_positions[sample.id],
                line=dict(color=color_map['sample'], width=width_map['sample'])
            )
    
    # Test lines - from created_at to now
    for sample in individual.samples.all():
        for test in sample.tests.all():
            if test.id in test_positions:
                test_created = test.created_at.date().isoformat() if test.created_at else '2025-01-01'
                fig.add_shape(
                    type='line',
                    x0=test_created,
                    x1=date.today().isoformat(),
                    y0=test_positions[test.id],
                    y1=test_positions[test.id],
                    line=dict(color=color_map['test'], width=width_map['test'])
                )
    
    # Analysis lines - from created_at to now
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                if analysis.id in analysis_positions:
                    analysis_created = analysis.created_at.date().isoformat() if analysis.created_at else '2025-01-01'
                    fig.add_shape(
                        type='line',
                        x0=analysis_created,
                        x1=date.today().isoformat(),
                        y0=analysis_positions[analysis.id],
                        y1=analysis_positions[analysis.id],
                        line=dict(color=color_map['analysis'], width=width_map['analysis'])
                    )
    
    # Task lines - from created_at to due_date (or now if no due_date)
    for task in individual.tasks.all():
        if task.id in task_positions:
            task_created = task.created_at.date().isoformat() if task.created_at else '2025-01-01'
            task_end = task.due_date.isoformat() if task.due_date else date.today().isoformat()
            fig.add_shape(
                type='line',
                x0=task_created,
                x1=task_end,
                y0=task_positions[task.id],
                y1=task_positions[task.id],
                line=dict(color=color_map['task'], width=width_map['task'])
            )
    
    # Note lines - from created_at to now
    for note in individual.notes.all():
        if note.id in note_positions:
            note_created = note.created_at.date().isoformat() if note.created_at else '2025-01-01'
            fig.add_shape(
                type='line',
                x0=note_created,
                x1=date.today().isoformat(),
                y0=note_positions[note.id],
                y1=note_positions[note.id],
                line=dict(color=color_map['note'], width=width_map['note'])
            )
    
    # Sample task lines - from created_at to due_date (or now if no due_date)
    for sample in individual.samples.all():
        for task in sample.tasks.all():
            if task.id in task_positions:
                task_created = task.created_at.date().isoformat() if task.created_at else '2025-01-01'
                task_end = task.due_date.isoformat() if task.due_date else date.today().isoformat()
                fig.add_shape(
                    type='line',
                    x0=task_created,
                    x1=task_end,
                    y0=task_positions[task.id],
                    y1=task_positions[task.id],
                    line=dict(color=color_map['task'], width=width_map['task'])
                )
    
    # Sample note lines - from created_at to now
    for sample in individual.samples.all():
        for note in sample.notes.all():
            if note.id in note_positions:
                note_created = note.created_at.date().isoformat() if note.created_at else '2025-01-01'
                fig.add_shape(
                    type='line',
                    x0=note_created,
                    x1=date.today().isoformat(),
                    y0=note_positions[note.id],
                    y1=note_positions[note.id],
                    line=dict(color=color_map['note'], width=width_map['note'])
                )
    
    # Test task lines - from created_at to due_date (or now if no due_date)
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for task in test.tasks.all():
                if task.id in task_positions:
                    task_created = task.created_at.date().isoformat() if task.created_at else '2025-01-01'
                    task_end = task.due_date.isoformat() if task.due_date else date.today().isoformat()
                    fig.add_shape(
                        type='line',
                        x0=task_created,
                        x1=task_end,
                        y0=task_positions[task.id],
                        y1=task_positions[task.id],
                        line=dict(color=color_map['task'], width=width_map['task'])
                    )
    
    # Test note lines - from created_at to now
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for note in test.notes.all():
                if note.id in note_positions:
                    note_created = note.created_at.date().isoformat() if note.created_at else '2025-01-01'
                    fig.add_shape(
                        type='line',
                        x0=note_created,
                        x1=date.today().isoformat(),
                        y0=note_positions[note.id],
                        y1=note_positions[note.id],
                        line=dict(color=color_map['note'], width=width_map['note'])
                    )
    
    # Analysis task lines - from created_at to due_date (or now if no due_date)
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                for task in analysis.tasks.all():
                    if task.id in task_positions:
                        task_created = task.created_at.date().isoformat() if task.created_at else '2025-01-01'
                        task_end = task.due_date.isoformat() if task.due_date else date.today().isoformat()
                        fig.add_shape(
                            type='line',
                            x0=task_created,
                            x1=task_end,
                            y0=task_positions[task.id],
                            y1=task_positions[task.id],
                            line=dict(color=color_map['task'], width=width_map['task'])
                        )
    
    # Analysis note lines - from created_at to now
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                for note in analysis.notes.all():
                    if note.id in note_positions:
                        note_created = note.created_at.date().isoformat() if note.created_at else '2025-01-01'
                        fig.add_shape(
                            type='line',
                            x0=note_created,
                            x1=date.today().isoformat(),
                            y0=note_positions[note.id],
                            y1=note_positions[note.id],
                            line=dict(color=color_map['note'], width=width_map['note'])
                        )
    

    
    # Add vertical lines connecting object creation points hierarchically
    # Sample creation vertical lines - connect to individual
    for sample in individual.samples.all():
        if sample.id in sample_positions:
            sample_created = sample.created_at.date().isoformat() if sample.created_at else '2025-01-01'
            fig.add_shape(
                type='line',
                x0=sample_created,
                x1=sample_created,
                y0=0,  # Individual timeline
                y1=sample_positions[sample.id],  # Sample position
                line=dict(color=color_map['sample'], width=width_map['sample'], dash='dot')
            )
    
    # Test creation vertical lines - connect to their sample
    for sample in individual.samples.all():
        for test in sample.tests.all():
            if test.id in test_positions and sample.id in sample_positions:
                test_created = test.created_at.date().isoformat() if test.created_at else '2025-01-01'
                fig.add_shape(
                    type='line',
                    x0=test_created,
                    x1=test_created,
                    y0=sample_positions[sample.id],  # Sample position
                    y1=test_positions[test.id],  # Test position
                    line=dict(color=color_map['test'], width=width_map['test'], dash='dot')
                )
    
    # Analysis creation vertical lines - connect to their test
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                if analysis.id in analysis_positions and test.id in test_positions:
                    analysis_created = analysis.created_at.date().isoformat() if analysis.created_at else '2025-01-01'
                    fig.add_shape(
                        type='line',
                        x0=analysis_created,
                        x1=analysis_created,
                        y0=test_positions[test.id],  # Test position
                        y1=analysis_positions[analysis.id],  # Analysis position
                        line=dict(color=color_map['analysis'], width=width_map['analysis'], dash='dot')
                    )
    
    # Task creation vertical lines - connect to individual
    for task in individual.tasks.all():
        if task.id in task_positions:
            task_created = task.created_at.date().isoformat() if task.created_at else '2025-01-01'
            fig.add_shape(
                type='line',
                x0=task_created,
                x1=task_created,
                y0=0,  # Individual timeline
                y1=task_positions[task.id],  # Task position
                line=dict(color=color_map['task'], width=width_map['task'], dash='dot')
            )
    
    # Note creation vertical lines - connect to individual
    for note in individual.notes.all():
        if note.id in note_positions:
            note_created = note.created_at.date().isoformat() if note.created_at else '2025-01-01'
            fig.add_shape(
                type='line',
                x0=note_created,
                x1=note_created,
                y0=0,  # Individual timeline
                y1=note_positions[note.id],  # Note position
                line=dict(color=color_map['note'], width=width_map['note'], dash='dot')
            )
    
    # Sample task creation vertical lines - connect to sample
    for sample in individual.samples.all():
        for task in sample.tasks.all():
            if task.id in task_positions and sample.id in sample_positions:
                task_created = task.created_at.date().isoformat() if task.created_at else '2025-01-01'
                fig.add_shape(
                    type='line',
                    x0=task_created,
                    x1=task_created,
                    y0=sample_positions[sample.id],  # Sample position
                    y1=task_positions[task.id],  # Task position
                    line=dict(color=color_map['task'], width=width_map['task'], dash='dot')
                )
    
    # Sample note creation vertical lines - connect to sample
    for sample in individual.samples.all():
        for note in sample.notes.all():
            if note.id in note_positions and sample.id in sample_positions:
                note_created = note.created_at.date().isoformat() if note.created_at else '2025-01-01'
                fig.add_shape(
                    type='line',
                    x0=note_created,
                    x1=note_created,
                    y0=sample_positions[sample.id],  # Sample position
                    y1=note_positions[note.id],  # Note position
                    line=dict(color=color_map['note'], width=width_map['note'], dash='dot')
                )
    
    # Test task creation vertical lines - connect to test
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for task in test.tasks.all():
                if task.id in task_positions and test.id in test_positions:
                    task_created = task.created_at.date().isoformat() if task.created_at else '2025-01-01'
                    fig.add_shape(
                        type='line',
                        x0=task_created,
                        x1=task_created,
                        y0=test_positions[test.id],  # Test position
                        y1=task_positions[task.id],  # Task position
                        line=dict(color=color_map['task'], width=width_map['task'], dash='dot')
                    )
    
    # Test note creation vertical lines - connect to test
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for note in test.notes.all():
                if note.id in note_positions and test.id in test_positions:
                    note_created = note.created_at.date().isoformat() if note.created_at else '2025-01-01'
                    fig.add_shape(
                        type='line',
                        x0=note_created,
                        x1=note_created,
                        y0=test_positions[test.id],  # Test position
                        y1=note_positions[note.id],  # Note position
                        line=dict(color=color_map['note'], width=width_map['note'], dash='dot')
                    )
    
    # Analysis task creation vertical lines - connect to analysis
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                for task in analysis.tasks.all():
                    if task.id in task_positions and analysis.id in analysis_positions:
                        task_created = task.created_at.date().isoformat() if task.created_at else '2025-01-01'
                        fig.add_shape(
                            type='line',
                            x0=task_created,
                            x1=task_created,
                            y0=analysis_positions[analysis.id],  # Analysis position
                            y1=task_positions[task.id],  # Task position
                            line=dict(color=color_map['task'], width=width_map['task'], dash='dot')
                        )
    
    # Analysis note creation vertical lines - connect to analysis
    for sample in individual.samples.all():
        for test in sample.tests.all():
            for analysis in test.analyses.all():
                for note in analysis.notes.all():
                    if note.id in note_positions and analysis.id in analysis_positions:
                        note_created = note.created_at.date().isoformat() if note.created_at else '2025-01-01'
                        fig.add_shape(
                            type='line',
                            x0=note_created,
                            x1=note_created,
                            y0=analysis_positions[analysis.id],  # Analysis position
                            y1=note_positions[note.id],  # Note position
                            line=dict(color=color_map['note'], width=width_map['note'], dash='dot')
                        )
    

    
    # Update layout
    fig.update_layout(
        title=f'Timeline for Individual {individual.individual_id}',
        xaxis_title='Date',
        yaxis_title='',
        showlegend=False,
        height=600,
        yaxis=dict(
            showticklabels=False,
            range=[min_y - 0.5, max_y + 0.5]
        ),
        xaxis=dict(
            tickangle=20,
            tickformat='%d %b %Y',
            type='date',
        ),
        # Add text angle for better readability
        annotations=[
            dict(
                x=date,
                y=y_pos + 0.1,  # Position just above each event's line
                text='',
                showarrow=False,
                textangle=0,
                font=dict(size=10),
                xanchor='left',
                yanchor='bottom'
            ) for date, desc, y_pos in zip(dates, descriptions, y_positions)
        ],
        hovermode='closest'
    )
    
    plot_json = json.dumps(fig.to_dict())
    
    context = {
        'individual': individual,
        'plot_json': plot_json,
        'timeline_events': timeline_events,
        'event_count': len(timeline_events)
    }
    
    if request.htmx:
        return render(request, 'lab/individual.html#timeline', context)
    else:
        return render(request, 'lab/individual.html', context)


@login_required
def plots_page(request):
    """View for the plots page showing various data visualizations."""
    from django.db.models import Count, Q
    from .models import Individual, Sample, Test, Analysis, Status, SampleType, TestType, AnalysisType, Institution
    import plotly.graph_objects as go
    import plotly.express as px
    import json
    
    # Apply global filters
    active_filters = request.session.get('active_filters', {})
    filter_conditions = Q()
    
    if active_filters:
        for filter_key, filter_values in active_filters.items():
            if filter_values:  # Only apply non-empty filters
                # Handle different filter types
                if isinstance(filter_values, list):
                    if filter_values:  # Non-empty list
                        filter_conditions &= Q(**{filter_key: filter_values[0]})  # Take first value for now
                else:
                    filter_conditions &= Q(**{filter_key: filter_values})
    
    # Get counts for stats cards with filters applied
    individuals_queryset = Individual.objects.all()
    samples_queryset = Sample.objects.all()
    tests_queryset = Test.objects.all()
    analyses_queryset = Analysis.objects.all()
    
    if filter_conditions:
        individuals_queryset = individuals_queryset.filter(filter_conditions)
        samples_queryset = samples_queryset.filter(filter_conditions)
        tests_queryset = tests_queryset.filter(filter_conditions)
        analyses_queryset = analyses_queryset.filter(filter_conditions)
    
    individuals_count = individuals_queryset.count()
    samples_count = samples_queryset.count()
    tests_count = tests_queryset.count()
    analyses_count = analyses_queryset.count()
    
    # Prepare distribution plots data
    distribution_plots = []
    
    # Get all data for the combined distribution plot
    individual_status_counts = individuals_queryset.values('status__name').annotate(count=Count('id')).order_by('-count')
    sample_status_counts = samples_queryset.values('status__name').annotate(count=Count('id')).order_by('-count')
    test_status_counts = tests_queryset.values('status__name').annotate(count=Count('id')).order_by('-count')
    analysis_status_counts = analyses_queryset.values('status__name').annotate(count=Count('id')).order_by('-count')
    
    # Get other distribution data
    sample_type_counts = samples_queryset.values('sample_type__name').annotate(count=Count('id')).order_by('-count')
    test_type_counts = tests_queryset.values('test_type__name').annotate(count=Count('id')).order_by('-count')
    analysis_type_counts = analyses_queryset.values('type__name').annotate(count=Count('id')).order_by('-count')
    institution_counts = individuals_queryset.values('institution__name').annotate(count=Count('id')).order_by('-count')
    
    # Create a combined distribution plot with all subplots
    traces = []
    positions = []
    subplot_titles = []
    
    # Color maps
    status_colors = {
        'Active': '#00cc96',      # Green
        'Registered': '#636EFA',   # Blue
        'Completed': '#FFA15A',    # Orange
        'Pending': '#ab63fa',      # Purple
        'Cancelled': '#EF553B',    # Red
        'Failed': '#FF6692',       # Pink
        'In Progress': '#19d3f3',  # Light Blue
        'On Hold': '#FECB52',      # Yellow
        'Archived': '#8c564b',     # Brown
        'Draft': '#B6E880',        # Light Green
    }
    
    # 1. Individual Status Distribution
    if individual_status_counts:
        labels = [item['status__name'] for item in individual_status_counts]
        values = [item['count'] for item in individual_status_counts]
        colors = [status_colors.get(item['status__name'], '#7f7f7f') for item in individual_status_counts]
            
        traces.append(go.Pie(
            labels=labels,
            values=values,
            hole=0.3,
            marker_colors=colors,
            name="Individual Status",
            domain={'row': 0, 'column': 0},
            textinfo='value',
            showlegend=True,
            legendgroup="individual_status"
        ))
        positions.append((0, 0))
        subplot_titles.append("Individual Status")
    
    # 2. Sample Status Distribution
    if sample_status_counts:
        labels = [item['status__name'] for item in sample_status_counts]
        values = [item['count'] for item in sample_status_counts]
        colors = [status_colors.get(item['status__name'], '#7f7f7f') for item in sample_status_counts]
        
        traces.append(go.Pie(
            labels=labels,
            values=values,
            hole=0.3,
            marker_colors=colors,
            name="Sample Status",
            domain={'row': 0, 'column': 1},
            textinfo='value',
            showlegend=True,
            legendgroup="sample_status"
        ))
        positions.append((0, 1))
        subplot_titles.append("Sample Status")
    
    # 3. Test Status Distribution
    if test_status_counts:
        labels = [item['status__name'] for item in test_status_counts]
        values = [item['count'] for item in test_status_counts]
        colors = [status_colors.get(item['status__name'], '#7f7f7f') for item in test_status_counts]
        
        traces.append(go.Pie(
            labels=labels,
            values=values,
            hole=0.3,
            marker_colors=colors,
            name="Test Status",
            domain={'row': 0, 'column': 2},
            textinfo='value',
            showlegend=True,
            legendgroup="test_status"
        ))
        positions.append((0, 2))
        subplot_titles.append("Test Status")
    
    # 4. Analysis Status Distribution
    if analysis_status_counts:
        labels = [item['status__name'] for item in analysis_status_counts]
        values = [item['count'] for item in analysis_status_counts]
        colors = [status_colors.get(item['status__name'], '#7f7f7f') for item in analysis_status_counts]
        
        traces.append(go.Pie(
            labels=labels,
            values=values,
            hole=0.3,
            marker_colors=colors,
            name="Analysis Status",
            domain={'row': 0, 'column': 3},
            textinfo='value',
            showlegend=True,
            legendgroup="analysis_status"
        ))
        positions.append((0, 3))
        subplot_titles.append("Analysis Status")
    
    # 5. Sample Type Distribution
    if sample_type_counts:
        labels = [item['sample_type__name'] for item in sample_type_counts]
        values = [item['count'] for item in sample_type_counts]
        
        traces.append(go.Pie(
            labels=labels,
            values=values,
            hole=0.3,
            marker_colors=['#00cc96', '#FFA15A', '#19d3f3', '#FF6692', '#B6E880', '#FF97FF'],
            name="Sample Type",
            domain={'row': 1, 'column': 0},
            textinfo='value',
            showlegend=True,
            legendgroup="sample_type"
        ))
        positions.append((1, 0))
        subplot_titles.append("Sample Type")
    
    # 6. Test Type Distribution
    if test_type_counts:
        labels = [item['test_type__name'] for item in test_type_counts]
        values = [item['count'] for item in test_type_counts]
        
        traces.append(go.Pie(
            labels=labels,
            values=values,
            hole=0.3,
            marker_colors=['#ab63fa', '#FF6692', '#B6E880', '#FF97FF', '#FECB52', '#636EFA'],
            name="Test Type",
            domain={'row': 1, 'column': 1},
            textinfo='value',
            showlegend=True,
            legendgroup="test_type"
        ))
        positions.append((1, 1))
        subplot_titles.append("Test Type")
    
    # 7. Analysis Type Distribution
    if analysis_type_counts:
        labels = [item['type__name'] for item in analysis_type_counts]
        values = [item['count'] for item in analysis_type_counts]
        
        traces.append(go.Pie(
            labels=labels,
            values=values,
            hole=0.3,
            marker_colors=['#FFA15A', '#19d3f3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52'],
            name="Analysis Type",
            domain={'row': 1, 'column': 2},
            textinfo='value',
            showlegend=True,
            legendgroup="analysis_type"
        ))
        positions.append((1, 2))
        subplot_titles.append("Analysis Type")
    
    # 8. Institution Distribution
    if institution_counts:
        labels = [item['institution__name'] for item in institution_counts]
        values = [item['count'] for item in institution_counts]
        
        traces.append(go.Pie(
            labels=labels,
            values=values,
            hole=0.3,
            marker_colors=['#636EFA', '#EF553B', '#00cc96', '#ab63fa', '#FFA15A', '#19d3f3'],
            name="Institution",
            domain={'row': 1, 'column': 3},
            textinfo='value',
            showlegend=True,
            legendgroup="institution"
        ))
        positions.append((1, 3))
        subplot_titles.append("Institution")
    
    # Create the combined subplot figure
    if traces:
        # Create subplot layout
        fig = go.Figure(data=traces)
        
        # Calculate grid dimensions (2 rows, 4 columns)
        fig.update_layout(
            height=900,
            template=None,
            grid=dict(
                rows=2,
                columns=4,
                pattern='independent'
            ),
            showlegend=True,
            margin=dict(l=50, r=50, t=100, b=50)
        )
        
        # Add subplot titles with better positioning
        annotations = []
        title_positions = [
            (0.125, 0.98, "Individual Status"),
            (0.375, 0.98, "Sample Status"),
            (0.625, 0.98, "Test Status"),
            (0.875, 0.98, "Analysis Status"),
            (0.125, 0.48, "Sample Type"),
            (0.375, 0.48, "Test Type"),
            (0.625, 0.48, "Analysis Type"),
            (0.875, 0.48, "Institution")
        ]
        
        for i, (x, y, title) in enumerate(title_positions):
            if i < len(subplot_titles):
                annotations.append(dict(
                    text=subplot_titles[i],
                    x=x,
                    y=y,
                    xref='paper',
                    yref='paper',
                    showarrow=False,
                    font=dict(size=16, color='black', weight='bold'),
                    xanchor='center',
                    yanchor='top'
                ))
        
        fig.update_layout(annotations=annotations)
        
        # Convert the figure to dict and ensure proper JSON serialization
        chart_dict = fig.to_dict()
        
        distribution_plots.append({
            'id': 'combined-distributions',
            'title': 'All Distributions',
            'icon': 'chart-pie',
            'chart_data': chart_dict,
            'stats': [
                {'label': 'Total Individuals', 'value': individuals_count},
                {'label': 'Total Samples', 'value': samples_count},
                {'label': 'Total Tests', 'value': tests_count},
                {'label': 'Total Analyses', 'value': analyses_count}
            ]
        })
    
    context = {
        'individuals_count': individuals_count,
        'samples_count': samples_count,
        'tests_count': tests_count,
        'analyses_count': analyses_count,
        'distribution_plots': distribution_plots,
    }

    
    if request.htmx:
        return render(request, 'lab/plots.html#plots-content', context)
    else:
        return render(request, 'lab/plots.html', context)


@login_required
def pie_chart_view(request, model_name, attribute_name):
    """
    Generate a pie chart for any model and attribute combination.
    
    Args:
        model_name: The name of the Django model (e.g., 'Individual', 'Sample')
        attribute_name: The name of the attribute to group by (e.g., 'status__name', 'type__name')
    """
    from django.apps import apps
    from django.db.models import Count, Q
    import plotly.graph_objects as go
    import json
    
    try:
        # Get the model class
        model_class = apps.get_model('lab', model_name)
        
        # Validate that the attribute exists
        if not hasattr(model_class, attribute_name.split('__')[0]):
            return JsonResponse({
                'error': f'Attribute "{attribute_name}" does not exist on model "{model_name}"'
            }, status=400)
        
        # Start with base queryset
        queryset = model_class.objects.all()
        
        # Apply global filters
        active_filters = request.session.get('active_filters', {})
        if active_filters:
            filter_conditions = Q()
            
            for filter_key, filter_values in active_filters.items():
                if filter_values:  # Only apply non-empty filters
                    # Handle different filter types
                    if isinstance(filter_values, list):
                        if filter_values:  # Non-empty list
                            filter_conditions &= Q(**{filter_key: filter_values[0]})  # Take first value for now
                    else:
                        filter_conditions &= Q(**{filter_key: filter_values})
            
            if filter_conditions:
                queryset = queryset.filter(filter_conditions)
        
        # Get the data with filters applied
        queryset = queryset.values(attribute_name).annotate(count=Count('id')).order_by('-count')
        
        if not queryset:
            return JsonResponse({
                'error': f'No data found for {model_name}.{attribute_name}'
            }, status=404)
        
        # Prepare data for pie chart
        labels = []
        values = []
        
        for item in queryset:
            # Handle None values
            label = item[attribute_name] if item[attribute_name] is not None else 'Unknown'
            labels.append(str(label))
            values.append(item['count'])
        
        # Create pie chart
        fig = go.Figure(data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.3,  # Creates a donut chart
                textinfo='value',
                textposition='outside',
                marker=dict(colors=['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F'])
            )
        ])
        
        fig.update_layout(
            title=f'{model_name} Distribution by {attribute_name.replace("__", " ").title()}',
            height=400,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        # Calculate percentages
        total = sum(values)
        data_with_percentages = []
        for label, value in zip(labels, values):
            percentage = (value / total * 100) if total > 0 else 0
            data_with_percentages.append((label, value, percentage))
        
        # Prepare response data
        chart_data = {
            'chart_json': json.dumps(fig.to_dict()),
            'model_name': model_name,
            'attribute_name': attribute_name,
            'total_count': total,
            'unique_values': len(values),
            'data': data_with_percentages
        }
        
        if request.htmx:
            return render(request, 'lab/pie_chart_partial.html', chart_data)
        else:
            return render(request, 'lab/pie_chart.html', chart_data)
            
    except LookupError:
        return JsonResponse({
            'error': f'Model "{model_name}" not found in app "lab"'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'error': f'Error generating pie chart: {str(e)}'
        }, status=500)


@login_required
def get_stats_counts(request):
    from .models import Individual, Sample, Test, Analysis
    from django.db.models import Q
    active_filters = request.session.get('active_filters', {})
    filter_conditions = Q()
    if active_filters:
        for filter_key, filter_values in active_filters.items():
            if filter_values:
                if isinstance(filter_values, list):
                    if filter_values:
                        filter_conditions &= Q(**{filter_key: filter_values[0]})
                else:
                    filter_conditions &= Q(**{filter_key: filter_values})
    individuals_queryset = Individual.objects.all()
    samples_queryset = Sample.objects.all()
    tests_queryset = Test.objects.all()
    analyses_queryset = Analysis.objects.all()
    if filter_conditions:
        individuals_queryset = individuals_queryset.filter(filter_conditions)
        samples_queryset = samples_queryset.filter(filter_conditions)
        tests_queryset = tests_queryset.filter(filter_conditions)
        analyses_queryset = analyses_queryset.filter(filter_conditions)
    data = {
        'individuals': individuals_queryset.count(),
        'samples': samples_queryset.count(),
        'tests': tests_queryset.count(),
        'analyses': analyses_queryset.count(),
    }
    return JsonResponse(data)
