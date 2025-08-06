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
from .models import Individual

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
    
    # Get individual history and important dates
    for record in individual.history.all():
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
        for record in sample.history.all():
            timeline_events.append({
                'date': record.history_date,
                'type': 'sample',
                'action': record.get_history_type_display(),
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
            for record in test.history.all():
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
                for record in analysis.history.all():
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
        for record in task.history.all():
            timeline_events.append({
                'date': record.history_date,
                'type': 'task',
                'action': record.get_history_type_display(),
                'description': f"Task {record.get_history_type_display().lower()}",
                'user': record.history_user.username if record.history_user else 'System',
                'object_name': 'Task',
                'object_id': task.title,
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
                'object_id': task.title,
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
    
    timeline_events.sort(key=lambda x: x['date'], reverse=True)
    
    # Prepare data for Plotly timeline - convert to local time and assign hierarchical positions
    from django.utils import timezone
    
    # Create hierarchical positioning system
    sample_positions = {}  # Track sample IDs and their y-positions
    test_positions = {}    # Track test IDs and their y-positions
    analysis_positions = {} # Track analysis IDs and their y-positions
    
    # Assign y-positions based on hierarchy
    y_positions = []
    dates = []
    descriptions = []
    types = []
    users = []
    details = []
    
    for event in timeline_events:
        dates.append(timezone.localtime(event['date']).strftime('%Y-%m-%d %H:%M'))
        descriptions.append(event['description'])
        types.append(event['type'])
        users.append(event['user'])
        details.append(event['details'])
        
        # Determine y-position based on event type and hierarchy
        if event['type'] == 'individual':
            y_positions.append(0)  # Main timeline
        elif event['type'] == 'sample':
            # Extract sample ID from object_id (format: "Sample {id}")
            sample_id = event['object_id'].split()[-1] if ' ' in event['object_id'] else event['object_id']
            if sample_id not in sample_positions:
                # Assign new position above individual line
                sample_positions[sample_id] = len(sample_positions) + 1
            y_positions.append(sample_positions[sample_id])
        elif event['type'] == 'test':
            # Extract test ID from object_id (format: "Test {id}")
            test_id = event['object_id'].split()[-1] if ' ' in event['object_id'] else event['object_id']
            if test_id not in test_positions:
                # Assign new position above sample lines
                test_positions[test_id] = len(test_positions) + len(sample_positions) + 2
            y_positions.append(test_positions[test_id])
        elif event['type'] == 'analysis':
            # Extract analysis ID from object_id (format: "Analysis {id}")
            analysis_id = event['object_id'].split()[-1] if ' ' in event['object_id'] else event['object_id']
            if analysis_id not in analysis_positions:
                # Assign new position above test lines
                analysis_positions[analysis_id] = len(analysis_positions) + len(test_positions) + len(sample_positions) + 3
            y_positions.append(analysis_positions[analysis_id])
        elif event['type'] == 'task':
            y_positions.append(-1)  # Below individual line
        elif event['type'] == 'note':
            y_positions.append(-2)  # Below task line
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
    
    # Add horizontal lines for each level of the hierarchy with proper branching
    max_y = max(y_positions) if y_positions else 0
    min_y = min(y_positions) if y_positions else 0
    
    # Individual line (main timeline) - full width
    fig.add_shape(
        type='line',
        x0=dates[0] if dates else '2024-01-01',
        x1=dates[-1] if dates else '2024-12-31',
        y0=0,
        y1=0,
        line=dict(color='gray', width=2)
    )
    
    # Find creation events for proper branching
    sample_creation_dates = {}
    test_creation_dates = {}
    analysis_creation_dates = {}
    
    for i, event in enumerate(timeline_events):
        if event['type'] == 'sample' and event['action'] == 'Created':
            sample_id = event['object_id'].split()[-1] if ' ' in event['object_id'] else event['object_id']
            sample_creation_dates[sample_id] = dates[i]
        elif event['type'] == 'test' and event['action'] == 'Created':
            test_id = event['object_id'].split()[-1] if ' ' in event['object_id'] else event['object_id']
            test_creation_dates[test_id] = dates[i]
        elif event['type'] == 'analysis' and event['action'] == 'Created':
            analysis_id = event['object_id'].split()[-1] if ' ' in event['object_id'] else event['object_id']
            analysis_creation_dates[analysis_id] = dates[i]
    
    # Sample lines - start from creation event
    for sample_id, y_pos in sample_positions.items():
        start_date = sample_creation_dates.get(sample_id, dates[0] if dates else '2024-01-01')
        fig.add_shape(
            type='line',
            x0=start_date,
            x1=dates[-1] if dates else '2024-12-31',
            y0=y_pos,
            y1=y_pos,
            line=dict(color='lightblue', width=1, dash='dash')
        )
    
    # Test lines - start from creation event
    for test_id, y_pos in test_positions.items():
        start_date = test_creation_dates.get(test_id, dates[0] if dates else '2024-01-01')
        fig.add_shape(
            type='line',
            x0=start_date,
            x1=dates[-1] if dates else '2024-12-31',
            y0=y_pos,
            y1=y_pos,
            line=dict(color='lightgreen', width=1, dash='dot')
        )
    
    # Analysis lines - start from creation event
    for analysis_id, y_pos in analysis_positions.items():
        start_date = analysis_creation_dates.get(analysis_id, dates[0] if dates else '2024-01-01')
        fig.add_shape(
            type='line',
            x0=start_date,
            x1=dates[-1] if dates else '2024-12-31',
            y0=y_pos,
            y1=y_pos,
            line=dict(color='lightcoral', width=1, dash='dashdot')
        )
    
    # Task line - full width (or could be branched too if needed)
    if -1 in y_positions:
        fig.add_shape(
            type='line',
            x0=dates[0] if dates else '2024-01-01',
            x1=dates[-1] if dates else '2024-12-31',
            y0=-1,
            y1=-1,
            line=dict(color='lightgray', width=1, dash='dash')
        )
    
    # Note line - full width (or could be branched too if needed)
    if -2 in y_positions:
        fig.add_shape(
            type='line',
            x0=dates[0] if dates else '2024-01-01',
            x1=dates[-1] if dates else '2024-12-31',
            y0=-2,
            y1=-2,
            line=dict(color='lightyellow', width=1, dash='dot')
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
            tickangle=45,
            tickformat='%Y-%m-%d %H:%M'
        ),
        # Add text angle for better readability
        annotations=[
            dict(
                x=date,
                y=y_pos + 0.1,  # Position just above each event's line
                text=desc,
                showarrow=False,
                textangle=-70,  # Bottom-left to top-right orientation
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
    
    # 1. Individual Status Distribution
    status_counts = individuals_queryset.values('status__name').annotate(count=Count('id')).order_by('-count')
    if status_counts:
        fig = go.Figure(data=[
            go.Pie(
                labels=[item['status__name'] for item in status_counts],
                values=[item['count'] for item in status_counts],
                hole=0.3,
                marker_colors=['#636EFA', '#EF553B', '#00cc96', '#ab63fa', '#FFA15A', '#19d3f3']
            )
        ])
        fig.update_layout(
            title='Individual Status Distribution',
            height=300,
            template=None
        )
        
        distribution_plots.append({
            'id': 'individual-status',
            'title': 'Individual Status Distribution',
            'description': 'Distribution of individuals by their current status',
            'icon': 'users',
            'chart_data': fig.to_dict(),
            'stats': [
                {'label': 'Total Individuals', 'value': individuals_count},
                {'label': 'Active Statuses', 'value': status_counts.count()}
            ]
        })
    
    # 2. Sample Type Distribution
    sample_type_counts = samples_queryset.values('sample_type__name').annotate(count=Count('id')).order_by('-count')
    if sample_type_counts:
        fig = go.Figure(data=[
            go.Pie(
                labels=[item['sample_type__name'] for item in sample_type_counts],
                values=[item['count'] for item in sample_type_counts],
                hole=0.3,
                marker_colors=['#00cc96', '#FFA15A', '#19d3f3', '#FF6692', '#B6E880', '#FF97FF']
            )
        ])
        fig.update_layout(
            title='Sample Type Distribution',
            height=300,
            template=None
        )
        
        distribution_plots.append({
            'id': 'sample-type',
            'title': 'Sample Type Distribution',
            'description': 'Distribution of samples by their type',
            'icon': 'vial',
            'chart_data': fig.to_dict(),
            'stats': [
                {'label': 'Total Samples', 'value': samples_count},
                {'label': 'Sample Types', 'value': sample_type_counts.count()}
            ]
        })
    
    # 3. Test Type Distribution
    test_type_counts = tests_queryset.values('test_type__name').annotate(count=Count('id')).order_by('-count')
    if test_type_counts:
        fig = go.Figure(data=[
            go.Pie(
                labels=[item['test_type__name'] for item in test_type_counts],
                values=[item['count'] for item in test_type_counts],
                hole=0.3,
                marker_colors=['#ab63fa', '#FF6692', '#B6E880', '#FF97FF', '#FECB52', '#636EFA']
            )
        ])
        fig.update_layout(
            title='Test Type Distribution',
            height=300,
            template=None
        )
        
        distribution_plots.append({
            'id': 'test-type',
            'title': 'Test Type Distribution',
            'description': 'Distribution of tests by their type',
            'icon': 'flask-vial',
            'chart_data': fig.to_dict(),
            'stats': [
                {'label': 'Total Tests', 'value': tests_count},
                {'label': 'Test Types', 'value': test_type_counts.count()}
            ]
        })
    
    # 4. Analysis Type Distribution
    analysis_type_counts = analyses_queryset.values('type__name').annotate(count=Count('id')).order_by('-count')
    if analysis_type_counts:
        fig = go.Figure(data=[
            go.Pie(
                labels=[item['type__name'] for item in analysis_type_counts],
                values=[item['count'] for item in analysis_type_counts],
                hole=0.3,
                marker_colors=['#FFA15A', '#19d3f3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52']
            )
        ])
        fig.update_layout(
            title='Analysis Type Distribution',
            height=300,
            template=None
        )
        
        distribution_plots.append({
            'id': 'analysis-type',
            'title': 'Analysis Type Distribution',
            'description': 'Distribution of analyses by their type',
            'icon': 'laptop',
            'chart_data': fig.to_dict(),
            'stats': [
                {'label': 'Total Analyses', 'value': analyses_count},
                {'label': 'Analysis Types', 'value': analysis_type_counts.count()}
            ]
        })
    
    # 5. Institution Distribution
    institution_counts = individuals_queryset.values('institution__name').annotate(count=Count('id')).order_by('-count')
    if institution_counts:
        fig = go.Figure(data=[
            go.Pie(
                labels=[item['institution__name'] for item in institution_counts],
                values=[item['count'] for item in institution_counts],
                hole=0.3,
                marker_colors=['#636EFA', '#EF553B', '#00cc96', '#ab63fa', '#FFA15A', '#19d3f3']
            )
        ])
        fig.update_layout(
            title='Institution Distribution',
            height=300,
            template=None
        )
        
        distribution_plots.append({
            'id': 'institution',
            'title': 'Institution Distribution',
            'description': 'Distribution of individuals by institution',
            'icon': 'building-columns',
            'chart_data': fig.to_dict(),
            'stats': [
                {'label': 'Total Individuals', 'value': individuals_count},
                {'label': 'Institutions', 'value': institution_counts.count()}
            ]
        })
    
    # 6. Sample Status Distribution
    sample_status_counts = samples_queryset.values('status__name').annotate(count=Count('id')).order_by('-count')
    if sample_status_counts:
        fig = go.Figure(data=[
            go.Pie(
                labels=[item['status__name'] for item in sample_status_counts],
                values=[item['count'] for item in sample_status_counts],
                hole=0.3,
                marker_colors=['#00cc96', '#FFA15A', '#19d3f3', '#FF6692', '#B6E880', '#FF97FF']
            )
        ])
        fig.update_layout(
            title='Sample Status Distribution',
            height=300,
            template=None
        )
        
        distribution_plots.append({
            'id': 'sample-status',
            'title': 'Sample Status Distribution',
            'description': 'Distribution of samples by their current status',
            'icon': 'vial',
            'chart_data': fig.to_dict(),
            'stats': [
                {'label': 'Total Samples', 'value': samples_count},
                {'label': 'Active Statuses', 'value': sample_status_counts.count()}
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
                textinfo='label+percent',
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
