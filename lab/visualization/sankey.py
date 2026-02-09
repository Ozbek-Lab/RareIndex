from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from lab.models import Individual, Sample, Test, Pipeline, Analysis, TestType, PipelineType, AnalysisType, SampleType, Institution
import json

def generate_sankey_data(sankey_metrics):
    """
    Generate data for a Sankey diagram showing the flow:
    Individual → Sample → Test → PipelineType
    Filters are applied for indexes_only, institution, sample_types, test_types, pipeline_types.
    Returns a dict suitable for plotly.graph_objects.Figure().to_dict()
    """
    from collections import defaultdict
    import plotly.graph_objects as go

    # Initial base queryset for individuals
    if sankey_metrics['indexes_only']:
        individuals = list(Individual.objects.exclude(is_index=None).filter(is_index=True))
    else:
        individuals = list(Individual.objects.all())
    if sankey_metrics['institution']:
        individuals = [ind for ind in individuals if ind.sending_institution_id == sankey_metrics['institution']]

    # Start with all samples, tests, pipelines
    samples = list(Sample.objects.select_related('individual').all())
    tests = list(Test.objects.select_related('sample', 'test_type').all())
    pipelines = list(Pipeline.objects.select_related('test', 'type').all())

    # Apply sample_types filter
    if sankey_metrics['sample_types']:
        samples = [s for s in samples if s.sample_type_id in sankey_metrics['sample_types']]
        # Only keep individuals that have at least one sample
        sample_individual_ids = set(s.individual_id for s in samples if s.individual_id)
        individuals = [ind for ind in individuals if ind.id in sample_individual_ids]

    # Apply test_types filter
    if sankey_metrics['test_types']:
        tests = [t for t in tests if t.test_type_id in sankey_metrics['test_types']]
        # Only keep samples that have at least one test
        test_sample_ids = set(t.sample_id for t in tests if t.sample_id)
        samples = [s for s in samples if s.id in test_sample_ids]
        # Only keep individuals that have at least one sample (after test filter)
        sample_individual_ids = set(s.individual_id for s in samples if s.individual_id)
        individuals = [ind for ind in individuals if ind.id in sample_individual_ids]

    # Apply pipeline_types filter
    if sankey_metrics['pipeline_types']:
        pipelines = [p for p in pipelines if p.type_id in sankey_metrics['pipeline_types']]
        # Only keep tests that have at least one pipeline
        pipeline_test_ids = set(p.test_id for p in pipelines if p.test_id)
        tests = [t for t in tests if t.id in pipeline_test_ids]
        # Only keep samples that have at least one test (after pipeline filter)
        test_sample_ids = set(t.sample_id for t in tests if t.sample_id)
        samples = [s for s in samples if s.id in test_sample_ids]
        # Only keep individuals that have at least one sample (after pipeline filter)
        sample_individual_ids = set(s.individual_id for s in samples if s.individual_id)
        individuals = [ind for ind in individuals if ind.id in sample_individual_ids]

    # Build node labels and index mapping
    node_labels = []
    node_index = {}
    
    # Individuals
    for ind in individuals:
        label = f"Individual: {ind.full_name}" if ind.full_name else f"Individual {ind.id}"
        if label not in node_index:
            node_index[label] = len(node_labels)
            node_labels.append(label)
    # Samples
    for s in samples:
        label = f"Sample: {s.sample_type.name}" if s.sample_type else f"Sample {s.id}"
        if label not in node_index:
            node_index[label] = len(node_labels)
            node_labels.append(label)
    # Tests
    for t in tests:
        label = f"Test: {t.test_type.name}" if t.test_type else f"Test {t.id}"
        if label not in node_index:
            node_index[label] = len(node_labels)
            node_labels.append(label)
    # Pipeline Types
    for p in pipelines:
        label = f"Pipeline: {p.type.name}" if p.type else f"Pipeline {p.id}"
        if label not in node_index:
            node_index[label] = len(node_labels)
            node_labels.append(label)

    # Build links (source, target, value)
    link_counts = defaultdict(int)
    # Individual → Sample
    for s in samples:
        if s.individual:
            # Only include links from individuals in the filtered set
            if s.individual in individuals:
                ind_label = f"Individual: {s.individual.full_name}" if s.individual.full_name else f"Individual {s.individual.id}"
                sample_label = f"Sample: {s.sample_type.name}" if s.sample_type else f"Sample {s.id}"
                link_counts[(ind_label, sample_label)] += 1
    # Sample → Test
    for t in tests:
        if t.sample:
            sample_label = (
                f"Sample: {t.sample.sample_type.name}" if t.sample.sample_type else f"Sample {t.sample.id}"
            )
            test_label = f"Test: {t.test_type.name}" if t.test_type else f"Test {t.id}"
            link_counts[(sample_label, test_label)] += 1
    # Test → PipelineType
    for p in pipelines:
        if p.test and p.type:
            test_label = f"Test: {p.test.test_type.name}" if p.test.test_type else f"Test {p.test.id}"
            pipeline_label = f"Pipeline: {p.type.name}" if p.type else f"Pipeline {p.id}"
            link_counts[(test_label, pipeline_label)] += 1

    # Prepare source, target, value lists
    sources = []
    targets = []
    values = []
    for (src, tgt), val in link_counts.items():
        if src in node_index and tgt in node_index:
            sources.append(node_index[src])
            targets.append(node_index[tgt])
            values.append(val)

    # Build Plotly Sankey figure
    sankey_data = go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color="black", width=0.5),
            label=node_labels,
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
        ),
    )
    fig = go.Figure(data=[sankey_data])
    fig.update_layout(title_text="Sample/Test/Pipeline Flow", font_size=12, height=800)
    return fig.to_dict()

def generate_sankey_data_tests(sankey_metrics):
    """
    Sankey with 3 columns:
    1. Individuals: 'Index', 'Family'
    2. Test Types (all unique in filtered data)
    3. Pipeline Types (all unique in filtered data)
    """
    import plotly.graph_objects as go
    from collections import Counter, defaultdict
    import plotly.colors

    # Filtering (as before)
    if sankey_metrics['indexes_only']:
        individuals = Individual.objects.exclude(is_index=None).filter(is_index=True)
    else:
        individuals = Individual.objects.all()
    if sankey_metrics['institution']:
        individuals = individuals.filter(sending_institution_id=sankey_metrics['institution'])

    samples = Sample.objects.select_related('individual').filter(individual__in=individuals)
    if sankey_metrics['sample_types']:
        samples = samples.filter(sample_type_id__in=sankey_metrics['sample_types'])
        sample_individual_ids = set(s.individual_id for s in samples if s.individual_id)
        individuals = individuals.filter(id__in=sample_individual_ids)

    tests = Test.objects.select_related('sample', 'test_type').filter(sample__in=samples)
    if sankey_metrics['test_types']:
        tests = tests.filter(test_type_id__in=sankey_metrics['test_types'])
        test_sample_ids = set(t.sample_id for t in tests if t.sample_id)
        samples = samples.filter(id__in=test_sample_ids)
        sample_individual_ids = set(s.individual_id for s in samples if s.individual_id)
        individuals = individuals.filter(id__in=sample_individual_ids)

    pipelines = Pipeline.objects.select_related('test', 'type').filter(test__in=tests)
    if sankey_metrics['pipeline_types']:
        pipelines = pipelines.filter(type_id__in=sankey_metrics['pipeline_types'])

    # --- Build node lists ---
    # 1. Individuals: "Index", "Family"
    individual_nodes = ["Index", "Family"]

    # 2. Test Types
    test_type_names = sorted(set(t.test_type.name for t in tests if t.test_type))
    # 3. Pipeline Types
    pipeline_type_names = sorted(set(p.type.name for p in pipelines if p.type))

    # Build node_labels and index mapping
    node_labels = individual_nodes + test_type_names + pipeline_type_names
    node_index = {label: idx for idx, label in enumerate(node_labels)}

    # --- Build links ---
    # 1. Individual → Test Type
    link_counts_1 = Counter()
    for test in tests:
        if not test.sample or not test.sample.individual or not test.test_type:
            continue
        ind = test.sample.individual
        ind_node = "Index" if getattr(ind, "is_index", False) else "Family"
        test_node = test.test_type.name
        if test_node in test_type_names:
            link_counts_1[(ind_node, test_node)] += 1

    # 2. Test Type → Pipeline Type
    link_counts_2 = Counter()
    for pipeline in pipelines:
        if not pipeline.test or not pipeline.type or not pipeline.test.test_type:
            continue
        test_node = pipeline.test.test_type.name
        pipeline_node = pipeline.type.name
        if test_node in test_type_names and pipeline_node in pipeline_type_names:
            link_counts_2[(test_node, pipeline_node)] += 1

    # --- Build Sankey source, target, value lists ---
    sources = []
    targets = []
    values = []

    # Individual → Test Type
    for (src, tgt), count in link_counts_1.items():
        sources.append(node_index[src])
        targets.append(node_index[tgt])
        values.append(count)
    # Test Type → Pipeline Type
    for (src, tgt), count in link_counts_2.items():
        sources.append(node_index[src])
        targets.append(node_index[tgt])
        values.append(count)

    # Assign colors to nodes and links
    palette = plotly.colors.qualitative.Plotly
    node_colors = [palette[i % len(palette)] for i in range(len(node_labels))]
    link_colors = [node_colors[src] for src in sources]

    # Build Plotly Sankey figure
    sankey_data = go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color="black", width=0.5),
            label=node_labels,
            color=node_colors,
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=link_colors,
        ),
    )
    fig = go.Figure(data=[sankey_data])
    fig.update_layout(title_text="Individual → Test Type → Pipeline Type", font_size=12, height=800)
    return fig.to_dict()

@login_required
def sankey_visualization(request):
    indexes_only = request.GET.get('indexes_only') == '1'
    institution_id = request.GET.get('institution')
    # Get all type IDs
    all_test_type_ids = [tt.id for tt in TestType.objects.all()]
    all_pipeline_type_ids = [pt.id for pt in PipelineType.objects.all()]
    all_analysis_type_ids = [at.id for at in AnalysisType.objects.all()]
    all_sample_type_ids = [st.id for st in SampleType.objects.all()]
    # Parse advanced filter values as lists
    selected_test_types = request.GET.getlist('test_types')
    selected_pipeline_types = request.GET.getlist('pipeline_types')
    selected_analysis_types = request.GET.getlist('analysis_types')
    selected_sample_types = request.GET.getlist('sample_types')
    # If no filter is set, default to all checked
    test_types_checked = [int(x) for x in selected_test_types] if selected_test_types else all_test_type_ids
    pipeline_types_checked = [int(x) for x in selected_pipeline_types] if selected_pipeline_types else all_pipeline_type_ids
    analysis_types_checked = [int(x) for x in selected_analysis_types] if selected_analysis_types else all_analysis_type_ids
    sample_types_checked = [int(x) for x in selected_sample_types] if selected_sample_types else all_sample_type_ids
    sankey_metrics = {
        'indexes_only': indexes_only,
        'institution': int(institution_id) if institution_id else None,
        'test_types': test_types_checked,
        'pipeline_types': pipeline_types_checked,
        'analysis_types': analysis_types_checked,
        'sample_types': sample_types_checked,
    }
    # Determine if any filter is active
    filters_active = bool(selected_test_types or selected_pipeline_types or selected_analysis_types or selected_sample_types)
    plot_json = generate_sankey_data_tests(sankey_metrics)
    institutions = Institution.objects.all()
    test_types = TestType.objects.all()
    pipeline_types = PipelineType.objects.all()
    analysis_types = AnalysisType.objects.all()
    sample_types = SampleType.objects.all()
    
    template_name = "lab/visualization/sankey_visualization.html"
    if request.headers.get("HX-Request"):
        template_name += "#sankey-diagram"
    return render(
        request,
        template_name,
        {
            "plot_json": json.dumps(plot_json),
            "sankey_metrics": sankey_metrics,
            "institutions": institutions,
            "test_types": test_types,
            "pipeline_types": pipeline_types,
            "analysis_types": analysis_types,
            "sample_types": sample_types,
            "filters_active": filters_active,
        },
    )