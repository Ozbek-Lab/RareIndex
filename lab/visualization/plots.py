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
    from lab.models import Individual, Sample, Test, Pipeline, Analysis
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
    pipelines_queryset = Pipeline.objects.all()
    analyses_queryset = Analysis.objects.all()
    if filter_conditions:
        individuals_queryset = individuals_queryset.filter(filter_conditions)
        samples_queryset = samples_queryset.filter(filter_conditions)
        tests_queryset = tests_queryset.filter(filter_conditions)
        pipelines_queryset = pipelines_queryset.filter(filter_conditions)
        analyses_queryset = analyses_queryset.filter(filter_conditions)
    data = {
        'individuals': individuals_queryset.count(),
        'samples': samples_queryset.count(),
        'tests': tests_queryset.count(),
        'pipelines': pipelines_queryset.count(),
        'analyses': analyses_queryset.count(),
    }
    return JsonResponse(data)

@login_required
def plots_page(request):
    """View for the plots page showing various data visualizations."""
    from django.db.models import Count, Q
    from ..models import Individual, Sample, Test, Pipeline, Analysis, Status, SampleType, TestType, PipelineType, AnalysisType, Institution
    from variant.models import Variant, Classification
    from .hpo_network_visualization import process_hpo_data
    from ..filters import apply_filters
    import plotly.graph_objects as go
    import json
    import networkx as nx
    import fastobo
    
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

    # Check for partial update request
    chart_id = request.GET.get('chart_id')

    # Extract filter params from URL (query string)
    all_filters = {k: v for k, v in request.GET.items() if k.startswith("filter_")}

    # Base querysets (exclude placeholders)
    individuals_queryset = Individual.objects.all()
    samples_queryset = Sample.objects.all().exclude(sample_type__name="Placeholder")
    tests_queryset = Test.objects.all().exclude(sample__sample_type__name="Placeholder")
    pipelines_queryset = Pipeline.objects.all()
    analyses_queryset = Analysis.objects.all()

    # Apply URL-based global filters per model using the shared engine
    individuals_queryset = apply_filters(request, "Individual", individuals_queryset)
    samples_queryset = apply_filters(request, "Sample", samples_queryset)
    tests_queryset = apply_filters(request, "Test", tests_queryset)
    pipelines_queryset = apply_filters(request, "Pipeline", pipelines_queryset)
    analyses_queryset = apply_filters(request, "Analysis", analyses_queryset)
    
    variants_queryset = Variant.objects.all()

    # Helper function to generate a single chart's data
    def get_chart_data(target_chart_id):
        chart_data = None
        
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

        def create_pie_chart(items, label_key, colors_map=None, fixed_colors=None):
            if not items:
                return {'empty': True}
            labels = [item[label_key] if item[label_key] is not None else 'Unknown' for item in items]
            values = [item['count'] for item in items]
            
            colors = None
            if colors_map is not None:
                colors = [colors_map.get(item[label_key], '#7f7f7f') for item in items]
            elif fixed_colors is not None:
                colors = fixed_colors
                
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
            return fig.to_dict()

        if target_chart_id == 'individual-status':
            counts = individuals_queryset.values('status__name').annotate(count=Count('id', distinct=True)).order_by('-count')
            chart_data = create_pie_chart(counts, 'status__name', colors_map=status_colors)

        elif target_chart_id == 'sample-status':
            counts = samples_queryset.values('status__name').annotate(count=Count('id', distinct=True)).order_by('-count')
            chart_data = create_pie_chart(counts, 'status__name', colors_map=status_colors)
            
        elif target_chart_id == 'test-status':
            counts = tests_queryset.values('status__name').annotate(count=Count('id', distinct=True)).order_by('-count')
            chart_data = create_pie_chart(counts, 'status__name', colors_map=status_colors)
            
        elif target_chart_id == 'pipeline-status':
            counts = pipelines_queryset.values('status__name').annotate(count=Count('id', distinct=True)).order_by('-count')
            chart_data = create_pie_chart(counts, 'status__name', colors_map=status_colors)
            
        elif target_chart_id == 'analysis-status':
            counts = analyses_queryset.values('status__name').annotate(count=Count('id', distinct=True)).order_by('-count')
            chart_data = create_pie_chart(counts, 'status__name', colors_map=status_colors)
            
        elif target_chart_id == 'sample-type':
            counts = samples_queryset.values('sample_type__name').annotate(count=Count('id', distinct=True)).order_by('-count')
            chart_data = create_pie_chart(counts, 'sample_type__name', fixed_colors=['#00cc96', '#FFA15A', '#19d3f3', '#FF6692', '#B6E880', '#FF97FF'])
            
        elif target_chart_id == 'test-type':
            counts = tests_queryset.values('test_type__name').annotate(count=Count('id', distinct=True)).order_by('-count')
            chart_data = create_pie_chart(counts, 'test_type__name', fixed_colors=['#ab63fa', '#FF6692', '#B6E880', '#FF97FF', '#FECB52', '#636EFA'])
            
        elif target_chart_id == 'pipeline-type':
            counts = pipelines_queryset.values('type__name').annotate(count=Count('id', distinct=True)).order_by('-count')
            chart_data = create_pie_chart(counts, 'type__name', fixed_colors=['#FFA15A', '#19d3f3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52'])
            
        elif target_chart_id == 'analysis-type':
            counts = analyses_queryset.values('type__name').annotate(count=Count('id', distinct=True)).order_by('-count')
            chart_data = create_pie_chart(counts, 'type__name', fixed_colors=['#ab63fa', '#FF6692', '#B6E880', '#FF97FF', '#FECB52', '#636EFA'])
            
        elif target_chart_id == 'variant-status':
            counts = variants_queryset.values('status__name').annotate(count=Count('id', distinct=True)).order_by('-count')
            chart_data = create_pie_chart(counts, 'status__name', colors_map=status_colors)
            
        elif target_chart_id == 'variant-type':
            snv_count = variants_queryset.filter(snv__isnull=False).count()
            cnv_count = variants_queryset.filter(cnv__isnull=False).count()
            sv_count = variants_queryset.filter(sv__isnull=False).count()
            repeat_count = variants_queryset.filter(repeat__isnull=False).count()
            
            counts = [
                {'type': 'SNV', 'count': snv_count},
                {'type': 'CNV', 'count': cnv_count},
                {'type': 'SV', 'count': sv_count},
                {'type': 'Repeat', 'count': repeat_count},
            ]
            counts = [x for x in counts if x['count'] > 0]
            chart_data = create_pie_chart(counts, 'type', fixed_colors=['#636EFA', '#EF553B', '#00cc96', '#ab63fa'])
            
        elif target_chart_id == 'variant-classification':
            counts = Classification.objects.values('classification').annotate(count=Count('id')).order_by('-count')
            classification_display_map = dict(Classification.CLASSIFICATION_CHOICES)
            counts_data = []
            for item in counts:
                code = item['classification']
                count = item['count']
                display = classification_display_map.get(code, code)
                counts_data.append({'classification': display, 'count': count})
                
            classification_colors = {
                'Pathogenic': '#EF553B',       # Red
                'Likely Pathogenic': '#FFA15A', # Orange
                'VUS': '#FECB52',              # Yellow
                'Likely Benign': '#B6E880',    # Light Green
                'Benign': '#00cc96',           # Green
            }
            chart_data = create_pie_chart(counts_data, 'classification', colors_map=classification_colors)
            
        elif target_chart_id == 'institution':
            institution_counts = individuals_queryset.values('institution__name').annotate(count=Count('id', distinct=True)).order_by('-count')
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
                pass
            chart_data = create_pie_chart(institution_counts_aggregated, 'institution__name')
            
        elif target_chart_id == 'index-hpo-solved-status':
            index_individuals = individuals_queryset.filter(is_index=True)
            index_with_hpo_counts = []
            for individual in index_individuals.select_related('status').prefetch_related('hpo_terms'):
                hpo_count = len(individual.hpo_terms.all())
                status_name = individual.status.name if individual.status else 'Unknown'
                is_solved = status_name in ["Solved - P/LP", "Solved - VUS"]
                index_with_hpo_counts.append({
                    'hpo_count': hpo_count,
                    'is_solved': is_solved,
                })
            
            groups = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '15+']
            solved_counts = [0] * len(groups)
            unsolved_counts = [0] * len(groups)
            
            for item in index_with_hpo_counts:
                hpo_count = item['hpo_count']
                if hpo_count <= 15:
                    group_idx = hpo_count
                else:
                    group_idx = 16
                
                if item['is_solved']:
                    solved_counts[group_idx] += 1
                else:
                    unsolved_counts[group_idx] += 1
            
            if sum(solved_counts) + sum(unsolved_counts) > 0:
                fig = go.Figure()
                colors = ['#636EFA', '#EF553B', '#00cc96', '#FFA15A', '#ab63fa', '#FF6692']
                
                # Solved trace
                text_labels = [str(val) if val > 0 else '' for val in solved_counts]
                fig.add_trace(go.Bar(
                    name='Solved',
                    x=groups,
                    y=solved_counts,
                    marker_color=colors[0],
                    text=text_labels,
                    textposition='auto',
                    textfont=dict(size=10),
                ))
                
                # Unsolved trace
                text_labels = [str(val) if val > 0 else '' for val in unsolved_counts]
                fig.add_trace(go.Bar(
                    name='Unsolved',
                    x=groups,
                    y=unsolved_counts,
                    marker_color=colors[1],
                    text=text_labels,
                    textposition='auto',
                    textfont=dict(size=10),
                ))
                
                fig.update_layout(
                    barmode='group',
                    height=450,
                    showlegend=True,
                    margin=dict(l=50, r=20, t=60, b=80),
                    xaxis=dict(
                        title='Number of HPO Terms',
                        title_standoff=20,
                        type='category',
                        tickangle=0,
                        tickfont=dict(size=10),
                        showgrid=False,
                        automargin=True,
                    ),
                    yaxis=dict(
                        title='Count',
                        title_standoff=15,
                    ),
                    hovermode='x unified',
                )
                chart_data = fig.to_dict()
            else:
                # No data available - set empty flag to prevent repeated requests
                chart_data = {'empty': True}

        elif target_chart_id == 'hpo-terms':
            consolidated_hpo_counts, hpo_graph, hpo_object = process_hpo_data(individuals_queryset, threshold=hpo_threshold)
            
            if not consolidated_hpo_counts:
                # No data available - set empty flag to prevent repeated requests
                chart_data = {'empty': True}
            else:
                def get_term_name(term_id):
                    for frame in hpo_object:
                        if isinstance(frame, fastobo.term.TermFrame) and str(frame.id) == term_id:
                            for clause in frame:
                                if isinstance(clause, fastobo.term.NameClause):
                                    return str(clause.name)
                    return term_id

                root_node = "HP:0000118"
                sunburst_nodes = {}
                
                if root_node not in sunburst_nodes:
                     sunburst_nodes[root_node] = {
                        'id': root_node,
                        'label': 'Phenotypic Abnormality',
                        'parent': '',
                        'value': 0
                    }

                for term_id, count in consolidated_hpo_counts.items():
                    if term_id not in hpo_graph:
                        continue
                    
                    try:
                        path = nx.shortest_path(hpo_graph, term_id, root_node)
                        
                        if term_id not in sunburst_nodes:
                            sunburst_nodes[term_id] = {
                                'id': term_id,
                                'label': get_term_name(term_id),
                                'parent': path[1] if len(path) > 1 else '',
                                'value': 0
                            }
                        sunburst_nodes[term_id]['value'] += count
                        
                        for i in range(1, len(path)):
                            node = path[i]
                            if node not in sunburst_nodes:
                                parent = path[i+1] if i + 1 < len(path) else ''
                                sunburst_nodes[node] = {
                                    'id': node,
                                    'label': get_term_name(node),
                                    'parent': parent,
                                    'value': 0
                                }
                    except nx.NetworkXNoPath:
                        continue

                ids = [node['id'] for node in sunburst_nodes.values()]
                labels = [node['label'] for node in sunburst_nodes.values()]
                parents = [node['parent'] for node in sunburst_nodes.values()]
                values = [node['value'] for node in sunburst_nodes.values()]

                fig = go.Figure(go.Sunburst(
                    ids=ids,
                    labels=labels,
                    parents=parents,
                    values=values,
                    branchvalues="remainder",
                    hoverinfo="label+value+percent entry"
                ))
                
                fig.update_layout(
                    height=500, 
                    margin=dict(t=40, l=0, r=0, b=0),
                    sunburstcolorway=[
                        "#636EFA", "#EF553B", "#00cc96", "#ab63fa", "#FFA15A",
                        "#19d3f3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52"
                    ]
                )
                chart_data = fig.to_dict()

        return chart_data

    # Define all available plots with their metadata
    distribution_plots = [
        {'id': 'individual-status', 'title': 'Individual Status', 'icon': 'chart-pie'},
        {'id': 'sample-status', 'title': 'Sample Status', 'icon': 'chart-pie'},
        {'id': 'test-status', 'title': 'Test Status', 'icon': 'chart-pie'},
        {'id': 'pipeline-status', 'title': 'Pipeline Status', 'icon': 'chart-pie'},
        {'id': 'analysis-status', 'title': 'Analysis Status', 'icon': 'chart-pie'},
        {'id': 'sample-type', 'title': 'Sample Type', 'icon': 'chart-pie'},
        {'id': 'test-type', 'title': 'Test Type', 'icon': 'chart-pie'},
        {'id': 'pipeline-type', 'title': 'Pipeline Type', 'icon': 'chart-pie'},
        {'id': 'analysis-type', 'title': 'Analysis Type', 'icon': 'chart-pie'},
        {'id': 'hpo-terms', 'title': 'HPO Term Distribution', 'icon': 'dna'},
        {'id': 'variant-status', 'title': 'Variant Status', 'icon': 'dna'},
        {'id': 'variant-type', 'title': 'Variant Type', 'icon': 'dna'},
        {'id': 'variant-classification', 'title': 'Variant Classification', 'icon': 'dna'},
        {'id': 'institution', 'title': 'Institution', 'icon': 'chart-pie'},
        {'id': 'index-hpo-solved-status', 'title': 'Index Individuals by HPO Term Count', 'icon': 'chart-bar'},
    ]

    # If this is a request for a specific chart, return just that chart's partial
    if chart_id:
        target_plot = next((p for p in distribution_plots if p['id'] == chart_id), None)
        if target_plot:
            # Calculate data only for this chart
            target_plot['chart_data'] = get_chart_data(chart_id)
            
            # We need to wrap this in a list because the template expects a list
            context = {
                'distribution_plots': [target_plot],
                'hpoThreshold': hpo_threshold,
                'instituteThreshold': institute_threshold,
                'partial_render': True,
            }
            # Use a simplified template that just renders the plot items
            return render(request, 'lab/partials/single_plot.html', context)

    # Initial page load: Return metadata only, no chart data
    # The frontend will lazy load the data for each chart
    
    # Calculate quick stats (these are fast enough to keep)
    individuals_count = individuals_queryset.count()
    samples_count = samples_queryset.count()
    tests_count = tests_queryset.count()
    pipelines_count = pipelines_queryset.count()
    analyses_count = analyses_queryset.count()

    context = {
        'individuals_count': individuals_count,
        'samples_count': samples_count,
        'tests_count': tests_count,
        'pipelines_count': pipelines_count,
        'analyses_count': analyses_count,
        'distribution_plots': distribution_plots, # Contains only metadata, no 'chart_data'
        'all_filters': all_filters,
        'institute_threshold': institute_threshold,
        'hpo_threshold': hpo_threshold,
    }

    if request.htmx:
        return render(request, 'lab/plots.html#plots-section', context)
    else:
        return render(request, 'lab/index.html', context)


