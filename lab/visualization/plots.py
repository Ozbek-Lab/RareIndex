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

    # Create individual charts
    add_pie_plot(individual_status_counts, 'status__name', 'Individual Status', 'individual-status', colors_map=status_colors)
    add_pie_plot(sample_status_counts, 'status__name', 'Sample Status', 'sample-status', colors_map=status_colors)
    add_pie_plot(test_status_counts, 'status__name', 'Test Status', 'test-status', colors_map=status_colors)
    add_pie_plot(analysis_status_counts, 'status__name', 'Analysis Status', 'analysis-status', colors_map=status_colors)
    add_pie_plot(sample_type_counts, 'sample_type__name', 'Sample Type', 'sample-type', fixed_colors=['#00cc96', '#FFA15A', '#19d3f3', '#FF6692', '#B6E880', '#FF97FF'])
    add_pie_plot(test_type_counts, 'test_type__name', 'Test Type', 'test-type', fixed_colors=['#ab63fa', '#FF6692', '#B6E880', '#FF97FF', '#FECB52', '#636EFA'])
    add_pie_plot(analysis_type_counts, 'type__name', 'Analysis Type', 'analysis-type', fixed_colors=['#FFA15A', '#19d3f3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52'])
    # Aggregate small institution slices (<1%) into "Other"
    institution_counts_aggregated = institution_counts
    try:
        if institution_counts:
            counts_list = list(institution_counts)
            total_count = sum(item['count'] for item in counts_list) or 0
            if total_count > 0:
                major_items = []
                other_total = 0
                for item in counts_list:
                    if (item['count'] / total_count) < 0.01:
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
    
    context = {
        'individuals_count': individuals_count,
        'samples_count': samples_count,
        'tests_count': tests_count,
        'analyses_count': analyses_count,
        'distribution_plots': distribution_plots,
    }

    print("PLOTS PAGE")
    if request.htmx:
        return render(request, 'lab/plots.html#plots-section', context)
    else: # USELESS CODE?
        return render(request, 'lab/index.html', context)

def map_view(request):
    """
    Generate a scatter map visualization showing institutions of filtered individuals.
    Uses plotly.express scatter_mapbox to plot latitude and longitude values.
    """
    from django.db.models import Count, Q
    import plotly.express as px
    import json
    
    try:
        # Start with base queryset for individuals
        individuals_queryset = Individual.objects.all()
        
        # Get individual type filter from POST request
        individual_types = ['all']  # Default to all
        if request.method == 'POST':
            try:
                individual_types_data = request.POST.get('individual_types', '["all"]')
                individual_types = json.loads(individual_types_data)
                if not individual_types or 'all' in individual_types:
                    individual_types = ['all']
            except (json.JSONDecodeError, TypeError):
                individual_types = ['all']
        
        # Apply individual type filtering
        if individual_types != ['all']:
            if 'families' in individual_types:
                # Only one individual per family - get the first one from each family
                from django.db.models import Min
                # Get the minimum ID from each family to ensure one per family
                family_ids = individuals_queryset.filter(
                    family__isnull=False
                ).values('family').annotate(
                    first_individual_id=Min('id')
                ).values_list('first_individual_id', flat=True)
                
                individuals_queryset = individuals_queryset.filter(id__in=family_ids)
            elif 'probands' in individual_types:
                # Only probands selected
                individuals_queryset = individuals_queryset.filter(is_index=True)
        
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
                individuals_queryset = individuals_queryset.filter(filter_conditions)
        
        # Get each individual with their institution coordinates
        individuals_data = individuals_queryset.values(
            'id',
            'institution__name',
            'institution__latitude',
            'institution__longitude'
        ).filter(
            institution__latitude__isnull=False,
            institution__longitude__isnull=False,
            institution__latitude__gt=0,  # Filter out invalid coordinates
            institution__longitude__gt=0
        )
        
        if not individuals_data:
            if request.htmx or request.headers.get('Accept') == 'application/json':
                return JsonResponse({
                    'error': 'No institutions with valid coordinates found for the filtered individuals',
                    'individual_types': individual_types
                }, status=404)
            else:
                # For regular page requests, render the template with empty data
                return render(request, 'lab/map.html', {
                    'error_message': 'No institutions with valid coordinates found for the filtered individuals',
                    'individual_types': individual_types
                })
        
        # Prepare data for scatter map - each individual as a separate point
        df_data = []
        for item in individuals_data:
            df_data.append({
                'name': item['institution__name'],
                'lat': item['institution__latitude'],
                'long': item['institution__longitude'],
                'cnt': 1  # Each point represents 1 individual
            })
        
        if not df_data:
            if request.htmx or request.headers.get('Accept') == 'application/json':
                return JsonResponse({
                    'error': 'No valid institution data found for mapping',
                    'individual_types': individual_types
                }, status=404)
            else:
                # For regular page requests, render the template with empty data
                return render(request, 'lab/map.html', {
                    'error_message': 'No valid institution data found for mapping',
                    'individual_types': individual_types
                })
        
        # Create DataFrame-like structure for plotly
        import pandas as pd
        df = pd.DataFrame(df_data)
        
        # Add custom hover data for individuals
        df['individual_details'] = df['name']
        
        # Create tile-based scatter map (Mapbox)
        fig = px.scatter_map(
            df,
            lat="lat",
            lon="long",
            hover_name="name",
            hover_data=["cnt", "individual_details"],
            custom_data=["cnt", "individual_details"],
            zoom=5,
            title="City Distribution by Individual Count"
        )
        
        # Enable built-in clustering and basic styling (no custom sizing or labels)
        fig.update_traces(
            cluster=dict(enabled=True),
            marker=dict(
                color="#A3A6FF",
                opacity=0.9,
                showscale=False,
                size=20,
            ),
            hovertemplate="<b>%{customdata[1]}</b><br>" +
                         "<extra></extra>"
        )
        
        # Update layout for better appearance
        fig.update_layout(
            height=800,
            margin={"r":0,"t":30,"l":0,"b":0},
            title_x=0.5,
            # Use a label-rich, no-token basemap
            mapbox_style="carto-positron",
            mapbox=dict(
                center=dict(lat=39.0, lon=35.0),  # Center on Turkey
                zoom=4
            ),
            paper_bgcolor='rgba(0,0,0,0)',  # Transparent background
            plot_bgcolor='rgba(0,0,0,0)'    # Transparent plot area
        )
        
        # Prepare response data - ensure all data is JSON serializable
        try:
            # Convert Plotly figure to dict and ensure it's JSON serializable
            fig_dict = fig.to_dict()
            # Convert any numpy types to Python native/JSON-serializable types
            def convert_numpy_types(obj):
                try:
                    import numpy as np
                except Exception:
                    np = None
                
                if np is not None:
                    # numpy scalars
                    if isinstance(obj, (np.integer, np.floating, np.bool_)):
                        return obj.item()
                    # numpy arrays
                    if isinstance(obj, np.ndarray):
                        return obj.tolist()
                
                if isinstance(obj, dict):
                    return {k: convert_numpy_types(v) for k, v in obj.items()}
                elif isinstance(obj, (list, tuple)):
                    return [convert_numpy_types(item) for item in obj]
                else:
                    return obj
            
            fig_dict = convert_numpy_types(fig_dict)
            # print(fig_dict)
            
            # Aggregate counts for header stats
            institutions_count = individuals_queryset.filter(
                institution__isnull=False
            ).values('institution').distinct().count()
            families_count = individuals_queryset.filter(
                family__isnull=False
            ).values('family').distinct().count()
            probands_count = individuals_queryset.filter(is_index=True).count()

            chart_data = {
                'chart_json': json.dumps(fig_dict),
                'institution_count': institutions_count,
                'family_count': families_count,
                'proband_count': probands_count,
                'total_individuals': individuals_queryset.count(),
                'individual_types': individual_types,
                'applied_filters': {
                    'families_only': 'families' in individual_types,
                    'probands_only': 'probands' in individual_types,
                    'all_types': individual_types == ['all']
                }
            }
        except Exception as json_error:
            print("EXCEPTION: ", json_error)
            # Fallback: create a simpler chart structure
            # Aggregate counts for header stats (fallback path)
            institutions_count = individuals_queryset.filter(
                institution__isnull=False
            ).values('institution').distinct().count()
            families_count = individuals_queryset.filter(
                family__isnull=False
            ).values('family').distinct().count()
            probands_count = individuals_queryset.filter(is_index=True).count()

            chart_data = {
                'chart_json': json.dumps({
                    'data': [{
                        'type': 'scattergeo',
                        'lat': [float(item['lat']) for item in df_data],
                        'lon': [float(item['long']) for item in df_data],
                        'mode': 'markers+text',
                        'marker': {
                            'size': [20+int(item['cnt'])**0.7 for item in df_data],
                            'color': '#6366F1',
                            'opacity': 0.9
                        },
                        'text': [int(item['cnt']) for item in df_data],
                        'textfont': {'color': 'white', 'size': 10},
                        'textposition': 'middle center',
                        'hoverinfo': 'text+marker',
                        'hovertext': [f"<b>{item['name']}</b><br>Individual" for item in df_data]
                    }],
                    'layout': {
                        'geo': {
                            'scope': 'world',
                            'projection_type': 'equirectangular',
                            'showland': True,
                            'landcolor': 'rgb(248, 248, 248)',
                            'showocean': True,
                            'oceancolor': 'rgb(230, 240, 250)',
                            'showcountries': True,
                            'countrycolor': 'rgb(220, 220, 220)',
                            'showcoastlines': True,
                            'coastlinecolor': 'rgb(100, 100, 100)',
                            'showlakes': True,
                            'lakecolor': 'rgb(200, 220, 240)',
                            'showrivers': True,
                            'rivercolor': 'rgb(180, 200, 220)',
                            'center': {'lat': 39.0, 'lon': 35.0},
                            'lonaxis': {'range': [25, 45]},
                            'lataxis': {'range': [35, 43]},
                            'bgcolor': 'rgb(245, 245, 245)'
                        },
                        'height': 600,
                        'margin': {"r": 0, "t": 30, "l": 0, "b": 0},
                        'title': 'City Distribution by Individual Count'
                    }
                }),
                'institution_count': institutions_count,
                'family_count': families_count,
                'proband_count': probands_count,
                'total_individuals': individuals_queryset.count(),
                'individual_types': individual_types,
                'applied_filters': {
                    'families_only': 'families' in individual_types,
                    'probands_only': 'probands' in individual_types,
                    'all_types': individual_types == ['all']
                }
            }
        
        # Return JSON for API calls, render template for page requests
        if request.htmx or request.headers.get('Accept') == 'application/json':
            return JsonResponse(chart_data)
        else:
            return render(request, 'lab/map.html', chart_data)
        
    except Exception as e:
        if request.htmx or request.headers.get('Accept') == 'application/json':
            return JsonResponse({
                'error': f'Error generating map: {str(e)}',
                'individual_types': individual_types
            }, status=500)
        else:
            return render(request, 'lab/map.html', {
                'error_message': f'Error generating map: {str(e)}',
                'individual_types': individual_types
            })
