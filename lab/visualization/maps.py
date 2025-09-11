# Django and standard library imports
import json
from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Count, Q, Min

# Third-party library imports
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import math

# Make sure to import your Individual model
from lab.models import Individual


def generate_map_data(individuals_queryset, individual_types, enable_clustering=True):
    """
    Generate a scatter map visualization showing institutions of filtered individuals.
    """
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

    # Aggregate data by institution coordinates and sum the counts
    df_data = []
    institution_counts = {}

    for item in individuals_data:
        coord_key = (item['institution__latitude'], item['institution__longitude'])
        if coord_key in institution_counts:
            institution_counts[coord_key]['cnt'] += 1
        else:
            institution_counts[coord_key] = {
                'name': item['institution__name'],
                'lat': item['institution__latitude'],
                'long': item['institution__longitude'],
                'cnt': 1
            }

    # Convert aggregated data to list
    df_data = list(institution_counts.values())

    if not df_data:
        return {
            'error': 'No valid institution data found for mapping',
            'individual_types': individual_types
        }

    # Create DataFrame-like structure for plotly
    df = pd.DataFrame(df_data)

    # Add custom hover data for individuals
    df['individual_details'] = df['name']
    print(f"Aggregated DataFrame - {len(df)} unique institutions:")
    print(df.head())
    print(f"Total individuals: {df['cnt'].sum()}")

    # Use original coordinates - clustering handled by Plotly's built-in feature
    offset_lat_series = df["lat"].tolist()
    offset_lon_series = df["long"].tolist()

    # Marker sizes and color scale by count
    counts = df["cnt"].astype(float)
    min_cnt = float(counts.min())
    max_cnt = float(counts.max())
    sizes = counts.apply(lambda c: 10.0 + 6.0 * math.log2(c + 1.0))

    # Build figure using Plotly's built-in clustering
    fig = go.Figure()

    # Create scatter map with optional clustering
    scatter_trace = go.Scattermap(
        lat=offset_lat_series,
        lon=offset_lon_series,
        mode="markers+text",
        marker=dict(
            size=sizes,
            color=counts,
            colorscale="Turbo",
            cmin=min_cnt,
            cmax=max_cnt,
            opacity=0.9,
            showscale=True,
            colorbar=dict(title="Individuals")
        ),
        text=[f"{name} ({cnt})" for name, cnt in zip(df["name"], df["cnt"])],
        textposition="bottom right",
        textfont=dict(size=16),
        hovertemplate=None,
        hoverinfo="skip",
        customdata=list(zip(df["name"], df["cnt"])),
        name="Institutions",
    )

    # Add trace to figure first
    fig.add_trace(scatter_trace)
    
    # Apply clustering if enabled - update the trace after adding
    if enable_clustering:
        fig.update_traces(cluster=dict(
            enabled=True,
            color="rgba(255,20,147,0.8)",  # Vibrant magenta
            size=25,
            step=2  # Minimum points to create a cluster
        ))

    fig.update_layout(
        map=dict(
            style="carto-positron",
            zoom=1.8,
            center=dict(lat=float(df["lat"].mean()), lon=float(df["long"].mean())),
        ),
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h"),
        hovermode=False,
    )

    fig_dict = fig.to_dict()
    # Convert any numpy types to Python native/JSON-serializable types

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
