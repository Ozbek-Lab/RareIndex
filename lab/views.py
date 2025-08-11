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
def nl_search_page(request):
    """
    Standalone page for natural language search.
    """
    if request.headers.get("HX-Request"):
        # Return just the main content for HTMX insertion
        return render(request, "lab/nl_search.html#nl-search-content", {})
    else:
        # Return the full page for direct access
        return render(request, "lab/nl_search.html")
