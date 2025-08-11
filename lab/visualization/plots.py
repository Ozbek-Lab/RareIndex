from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

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

@login_required
def plots_page(request):
    """View for the plots page showing various data visualizations."""
    from django.db.models import Count, Q
    from ..models import Individual, Sample, Test, Analysis, Status, SampleType, TestType, AnalysisType, Institution
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