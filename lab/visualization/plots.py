from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from lab.models import Individual

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
    from lab.models import Individual, Sample, Test, Analysis
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
    samples_queryset = Sample.objects.all().exclude(sample_type__name="Placeholder")
    tests_queryset = Test.objects.all().exclude(sample__sample_type__name="Placeholder")
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
    print("Plots page view request", request)
    print("Plots page GET params:", dict(request.GET))
    """View for the plots page showing various data visualizations."""
    from django.db.models import Count, Q
    from ..models import Individual, Sample, Test, Analysis, Status, SampleType, TestType, AnalysisType, Institution
    from ..filters import apply_filters
    import plotly.graph_objects as go
    import plotly.express as px
    import json
    
    # Numeric threshold for grouping small institutions into "Other"
    try:
        institute_threshold = int(request.GET.get('institute_threshold', '0'))
        if institute_threshold < 0:
            institute_threshold = 0
        if institute_threshold > 10:
            institute_threshold = 10
    except Exception:
        institute_threshold = 0

    try:
        hpo_threshold = int(request.GET.get('hpo_threshold', '0'))
        if hpo_threshold < 0:
            hpo_threshold = 0
        if hpo_threshold > 10:
            hpo_threshold = 10
    except Exception:
        hpo_threshold = 0

    # Extract filter params from URL (query string)
    all_filters = {k: v for k, v in request.GET.items() if k.startswith("filter_")}
    print("Plots page active URL filters:", all_filters)

    # Base querysets (exclude placeholders)
    individuals_queryset = Individual.objects.all()
    samples_queryset = Sample.objects.all().exclude(sample_type__name="Placeholder")
    tests_queryset = Test.objects.all().exclude(sample__sample_type__name="Placeholder")
    analyses_queryset = Analysis.objects.all()

    # Apply URL-based global filters per model using the shared engine
    individuals_queryset = apply_filters(request, "Individual", individuals_queryset)
    samples_queryset = apply_filters(request, "Sample", samples_queryset)
    tests_queryset = apply_filters(request, "Test", tests_queryset)
    analyses_queryset = apply_filters(request, "Analysis", analyses_queryset)
    
    individuals_count = individuals_queryset.count()
    samples_count = samples_queryset.count()
    tests_count = tests_queryset.count()
    analyses_count = analyses_queryset.count()
    
    # Prepare distribution plots data
    distribution_plots = []
    
    # Get all data for the combined distribution plot
    individual_status_counts = individuals_queryset.values('status__name').annotate(count=Count('id', distinct=True)).order_by('-count')
    sample_status_counts = samples_queryset.values('status__name').annotate(count=Count('id', distinct=True)).order_by('-count')
    test_status_counts = tests_queryset.values('status__name').annotate(count=Count('id', distinct=True)).order_by('-count')
    analysis_status_counts = analyses_queryset.values('status__name').annotate(count=Count('id', distinct=True)).order_by('-count')
    
    # Get other distribution data
    sample_type_counts = samples_queryset.values('sample_type__name').annotate(count=Count('id', distinct=True)).order_by('-count')
    test_type_counts = tests_queryset.values('test_type__name').annotate(count=Count('id', distinct=True)).order_by('-count')
    analysis_type_counts = analyses_queryset.values('type__name').annotate(count=Count('id', distinct=True)).order_by('-count')
    institution_counts = individuals_queryset.values('institution__name').annotate(count=Count('id', distinct=True)).order_by('-count')

    # HPO term distribution (counts each individual-term association)
    raw_hpo_term_counts = list(
        individuals_queryset
        .filter(hpo_terms__isnull=False)
        .values('hpo_terms__identifier', 'hpo_terms__label')
        .annotate(count=Count('id', distinct=True))
        .order_by('-count')
    )
    hpo_term_counts = []
    other_hpo_total = 0
    if raw_hpo_term_counts:
        for item in raw_hpo_term_counts:
            identifier = item.get('hpo_terms__identifier')
            label = item.get('hpo_terms__label')
            if identifier:
                term_id = f"HP:{identifier}"
            else:
                term_id = 'Unknown'
            display_name = f"{term_id} - {label}" if label else term_id
            count = item['count'] or 0
            if hpo_threshold and (count < hpo_threshold):
                other_hpo_total += count
            else:
                hpo_term_counts.append({
                    'hpo_display': display_name,
                    'count': count,
                })
        if other_hpo_total > 0:
            hpo_term_counts.append({'hpo_display': 'Other', 'count': other_hpo_total})
    
    # Build individual plot figures instead of a combined subplot
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
    
    def add_pie_plot(items, label_key, title, plot_id, colors_map=None, fixed_colors=None, icon='chart-pie'):
        if not items:
            return
        labels = [item[label_key] if item[label_key] is not None else 'Unknown' for item in items]
        values = [item['count'] for item in items]
        if colors_map is not None:
            colors = [colors_map.get(item[label_key], '#7f7f7f') for item in items]
        elif fixed_colors is not None:
            colors = fixed_colors
        else:
            colors = None
        fig = go.Figure(data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.3,
                marker_colors=colors,
                textinfo='value'
            )
        ])
        fig.update_layout(height=450, showlegend=True, margin=dict(l=20, r=20, t=40, b=20))
        distribution_plots.append({
            'id': plot_id,
            'title': title,
            'icon': icon,
            'chart_data': fig.to_dict(),
        })
    
    def add_bar_plot(x_data, y_data_list, y_labels, title, plot_id, colors=None, icon='chart-bar'):
        """Add a grouped bar plot to distribution_plots."""
        if not x_data or not y_data_list:
            return
        fig = go.Figure()
        if colors is None:
            colors = ['#636EFA', '#EF553B', '#00cc96', '#FFA15A', '#ab63fa', '#FF6692']
        for i, (y_data, y_label) in enumerate(zip(y_data_list, y_labels)):
            # Only show text labels for non-zero values to avoid overlapping
            text_labels = [str(val) if val > 0 else '' for val in y_data]
            fig.add_trace(go.Bar(
                name=y_label,
                x=x_data,
                y=y_data,
                marker_color=colors[i % len(colors)],
                text=text_labels,
                textposition='auto',  # Use 'auto' to place labels inside if outside doesn't fit
                textfont=dict(size=10),
            ))
        fig.update_layout(
            barmode='group',
            height=450,
            showlegend=True,
            margin=dict(l=50, r=20, t=60, b=80),  # Increased margins for labels
            xaxis=dict(
                title='Number of HPO Terms',
                title_standoff=20,
                type='category',  # Treat as categorical to ensure all labels show
                tickangle=0,
                tickfont=dict(size=10),
                showgrid=False,
                automargin=True,  # Let Plotly automatically adjust margins
            ),
            yaxis=dict(
                title='Count',
                title_standoff=15,
            ),
            hovermode='x unified',
        )
        distribution_plots.append({
            'id': plot_id,
            'title': title,
            'icon': icon,
            'chart_data': fig.to_dict(),
        })

    # Create individual charts
    add_pie_plot(individual_status_counts, 'status__name', 'Individual Status', 'individual-status', colors_map=status_colors)
    add_pie_plot(sample_status_counts, 'status__name', 'Sample Status', 'sample-status', colors_map=status_colors)
    add_pie_plot(test_status_counts, 'status__name', 'Test Status', 'test-status', colors_map=status_colors)
    add_pie_plot(analysis_status_counts, 'status__name', 'Analysis Status', 'analysis-status', colors_map=status_colors)
    add_pie_plot(sample_type_counts, 'sample_type__name', 'Sample Type', 'sample-type', fixed_colors=['#00cc96', '#FFA15A', '#19d3f3', '#FF6692', '#B6E880', '#FF97FF'])
    add_pie_plot(test_type_counts, 'test_type__name', 'Test Type', 'test-type', fixed_colors=['#ab63fa', '#FF6692', '#B6E880', '#FF97FF', '#FECB52', '#636EFA'])
    add_pie_plot(analysis_type_counts, 'type__name', 'Analysis Type', 'analysis-type', fixed_colors=['#FFA15A', '#19d3f3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52'])
    add_pie_plot(hpo_term_counts, 'hpo_display', 'HPO Term Distribution', 'hpo-terms', icon='dna')
    # Aggregate small institution slices by numeric threshold into "Other"
    institution_counts_aggregated = institution_counts
    try:
        if institution_counts:
            counts_list = list(institution_counts)
            if institute_threshold and institute_threshold > 0:
                major_items = []
                other_total = 0
                for item in counts_list:
                    if (item['count'] or 0) < institute_threshold:
                        other_total += item['count']
                    else:
                        major_items.append(item)
                if other_total > 0:
                    major_items.append({'institution__name': 'Other', 'count': other_total})
                institution_counts_aggregated = major_items
    except Exception:
        institution_counts_aggregated = institution_counts
    # Let Plotly choose colors for variable-length data; avoid fixed colors here
    add_pie_plot(institution_counts_aggregated, 'institution__name', 'Institution', 'institution')
    
    # HPO Term Count vs Solved/Unsolved Barplot for Index Individuals
    index_individuals = individuals_queryset.filter(is_index=True)
    
    # Get all index individuals with their HPO term counts and status
    index_with_hpo_counts = []
    for individual in index_individuals.select_related('status').prefetch_related('hpo_terms'):
        # Use len() to utilize prefetched data instead of triggering a query
        hpo_count = len(individual.hpo_terms.all())
        status_name = individual.status.name if individual.status else 'Unknown'
        is_solved = status_name in ["Solved - P/LP", "Solved - VUS"]
        index_with_hpo_counts.append({
            'hpo_count': hpo_count,
            'is_solved': is_solved,
        })
    
    # Group by HPO count: 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 15+
    groups = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '15+']
    solved_counts = [0] * len(groups)
    unsolved_counts = [0] * len(groups)
    
    for item in index_with_hpo_counts:
        hpo_count = item['hpo_count']
        # Determine which group this belongs to
        if hpo_count <= 15:
            group_idx = hpo_count
        else:
            group_idx = 16  # 15+ group
        
        if item['is_solved']:
            solved_counts[group_idx] += 1
        else:
            unsolved_counts[group_idx] += 1
    
    # Only add the plot if there's data
    if sum(solved_counts) + sum(unsolved_counts) > 0:
        add_bar_plot(
            x_data=groups,
            y_data_list=[solved_counts, unsolved_counts],
            y_labels=['Solved', 'Unsolved'],
            title='Index Individuals by HPO Term Count',
            plot_id='index-hpo-solved-status',
            colors=['#00cc96', '#EF553B'],  # Green for solved, Red for unsolved
            icon='chart-bar'
        )
    
    context = {
        'individuals_count': individuals_count,
        'samples_count': samples_count,
        'tests_count': tests_count,
        'analyses_count': analyses_count,
        'distribution_plots': distribution_plots,
        'all_filters': all_filters,
        'institute_threshold': institute_threshold,
        'hpo_threshold': hpo_threshold,
    }

    print("PLOTS PAGE")
    if request.htmx:
        return render(request, 'lab/plots.html#plots-section', context)
    else: # USELESS CODE?
        return render(request, 'lab/index.html', context)


