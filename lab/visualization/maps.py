# Django and standard library imports
import json
from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Count, Q, Min

# Third-party library imports
import pandas as pd
import plotly.express as px

# Make sure to import your Individual model
from lab.models import Individual


def _convert_numpy_types(obj):
    """
    Recursively convert numpy types to Python native types for JSON serialization.
    """
    import numpy as np
    
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: _convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_convert_numpy_types(item) for item in obj]
    else:
        return obj


def generate_map_data(individuals_queryset, individual_types):
    """
    Generate a scatter map visualization showing institutions of filtered individuals.
    """
    try:
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
            return {
                'error': 'No institutions with valid coordinates found for the filtered individuals',
                'individual_types': individual_types
            }
        
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
            return {
                'error': 'No valid institution data found for mapping',
                'individual_types': individual_types
            }
        
        # Create DataFrame-like structure for plotly
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
            fig_dict = _convert_numpy_types(fig_dict)
            
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
            
            return chart_data
            
        except Exception as e:
            return {
                'error': f'Error preparing chart data: {str(e)}',
                'individual_types': individual_types
            }
        
    except Exception as e:
        return {
            'error': f'Error generating map: {str(e)}',
            'individual_types': individual_types
        }


def build_chart_response_data(fig, queryset, individual_types):
    """
    Aggregates final counts and prepares the dictionary for the JSON/template response.
    """
    return {
        'chart_json': fig.to_json(),
        'institution_count': queryset.values('institution').distinct().count(),
        'family_count': queryset.values('family').distinct().count(),
        'proband_count': queryset.filter(is_index=True).count(),
        'total_individuals': queryset.count(),
        'individual_types': individual_types,
        'applied_filters': {
            'families_only': 'families' in individual_types,
            'probands_only': 'probands' in individual_types,
            'all_types': individual_types == ['all']
        }
    }
