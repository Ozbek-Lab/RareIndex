"""
HPO (Human Phenotype Ontology) visualization utilities.

This module contains functions for loading, processing, and visualizing HPO terms
in a network graph format using NetworkX and Plotly.
"""

import networkx as nx
import urllib.request
import fastobo
import warnings
import plotly.graph_objects as go
import json


def load_hpo_ontology():
    """
    Load the HPO ontology from the OBO file and create a NetworkX graph.
    
    Returns:
        tuple: (graph, hpo) where graph is a NetworkX DiGraph and hpo is the fastobo object
    """
    obo_url = "https://purl.obolibrary.org/obo/hp.obo"
    graph = nx.DiGraph()

    with urllib.request.urlopen(obo_url) as response:
        hpo = fastobo.load(response)

    for frame in hpo:
        if isinstance(frame, fastobo.term.TermFrame):
            graph.add_node(str(frame.id))
            for clause in frame:
                if isinstance(clause, fastobo.term.IsAClause):
                    graph.add_edge(str(frame.id), str(clause.term))

    return graph, hpo


def consolidate_terms(graph, terms, threshold=3):
    """
    Consolidate rare HPO terms by finding their closest common ancestors.
    
    Args:
        graph: NetworkX graph of HPO terms
        terms: Dictionary of term_id -> count
        threshold: Minimum count threshold for consolidation
        
    Returns:
        dict: Consolidated term counts
    """
    # Create a working copy of the counts
    working_counts = terms.copy()

    # Check if all terms exist in the graph, remove those that don't
    invalid_terms = []
    for term in working_counts:
        if term not in graph:
            warnings.warn(
                f"The node {term} is not in the graph. Removing from consolidation."
            )
            invalid_terms.append(term)

    for term in invalid_terms:
        working_counts.pop(term, None)

    # Keep track of consolidation history
    consolidated_terms = {}  # Maps original term -> ancestor that replaced it

    # Continue until we can't consolidate further
    iteration = 0
    while True:
        iteration += 1

        # Get all current terms that are below threshold
        rare_terms = [
            term for term, count in working_counts.items() if count < threshold
        ]

        # If we have less than 2 rare terms, we can't consolidate further
        if len(rare_terms) < 2:
            break

        # Try to find a pair to consolidate
        consolidated_pair = False

        for i in range(len(rare_terms)):
            for j in range(i + 1, len(rare_terms)):
                term1 = rare_terms[i]
                term2 = rare_terms[j]

                # Find their closest common ancestor
                ancestor = find_closest_ancestor(graph, term1, term2)

                if ancestor:
                    # Calculate the combined count
                    combined_count = working_counts.get(term1, 0) + working_counts.get(
                        term2, 0
                    )

                    # Remove the consolidated terms from working counts
                    count1 = working_counts.pop(term1)
                    count2 = working_counts.pop(term2)

                    # Add or update the ancestor count
                    if ancestor in working_counts:
                        working_counts[ancestor] += combined_count
                    else:
                        working_counts[ancestor] = combined_count

                    # Update consolidation history
                    consolidated_terms[term1] = ancestor
                    consolidated_terms[term2] = ancestor

                    consolidated_pair = True
                    break

            if consolidated_pair:
                break

        # If we couldn't find any pair to consolidate, we're done
        if not consolidated_pair:
            break

    return working_counts


def find_closest_ancestor(graph, term1, term2):
    """
    Find the closest common ancestor of two HPO terms.
    
    Args:
        graph: NetworkX graph of HPO terms
        term1: First HPO term ID
        term2: Second HPO term ID
        
    Returns:
        str: Closest common ancestor term ID, or None if not found
    """
    # Check if both terms exist in the graph
    if term1 not in graph:
        warnings.warn(f"The node {term1} is not in the graph. Skipping this term.")
        return None
    if term2 not in graph:
        warnings.warn(f"The node {term2} is not in the graph. Skipping this term.")
        return None

    try:
        # Get all ancestors for each term
        ancestors1 = nx.descendants(graph, term1)
        ancestors1.add(term1)  # Include the term itself

        ancestors2 = nx.descendants(graph, term2)
        ancestors2.add(term2)  # Include the term itself

        # Find common ancestors
        common_ancestors = ancestors1.intersection(ancestors2)
        if not common_ancestors:
            return None

        common_ancestors = list(common_ancestors)
        try:
            common_ancestors.remove("HP:0000118")
            common_ancestors.remove("HP:0000001")
        except:
            pass

        # Find the closest common ancestor
        # (The one with the longest path from the root)
        root = "HP:0000118"  # HPO root term

        closest_ancestor = None
        max_distance = -1

        for ancestor in common_ancestors:
            try:
                distance = len(nx.shortest_path(graph, ancestor, root)) - 1
                if distance > max_distance:
                    max_distance = distance
                    closest_ancestor = ancestor
            except nx.NetworkXNoPath:
                continue

        return closest_ancestor

    except nx.NetworkXError as e:
        warnings.warn(f"NetworkX error: {e}. Skipping this pair.")
        return None


def plotly_hpo_network(graph, hpo, term_counts, output_file=None, min_count=1):
    """
    Create a Plotly network visualization of HPO terms.
    
    Args:
        graph: NetworkX graph of HPO terms
        hpo: Fastobo HPO object
        term_counts: Dictionary of term_id -> count
        output_file: Optional file path to save the plot
        min_count: Minimum count threshold for displaying terms
        
    Returns:
        tuple: (fig, subgraph) where fig is a Plotly figure and subgraph is the NetworkX subgraph
    """
    # Function to extract term name from the HPO ontology
    def get_term_name(term_id):
        for frame in hpo:
            if isinstance(frame, fastobo.term.TermFrame) and str(frame.id) == term_id:
                for clause in frame:
                    if isinstance(clause, fastobo.term.NameClause):
                        return str(clause.name)
        return term_id

    # Root node for phenotypic abnormality
    root_node = "HP:0000118"  # Phenotypic abnormality

    # Create a subgraph with terms and paths to root
    subgraph = nx.DiGraph()

    # Add nodes with their counts
    for term_id, count in term_counts.items():
        if term_id in graph and count >= min_count:
            name = get_term_name(term_id)
            name = name.replace("system", "sys.")
            name = name.replace("morphology", "morph.")
            name = name.replace("Abnormality of the", "")
            name = name.replace("abnormality", "")
            name = name.replace("Abnormality of", "")
            name = name.replace("Abnormal", "")

            if len(name) > 30:
                name = name[:27] + "..."
            subgraph.add_node(term_id, name=name, count=count, term_id=term_id)

            # Add path from this term to the root node
            try:
                path = nx.shortest_path(graph, term_id, root_node)
                for i in range(len(path) - 1):
                    source = path[i]
                    target = path[i + 1]

                    if source not in subgraph:
                        subgraph.add_node(
                            source,
                            name=get_term_name(source),
                            count=term_counts.get(source, 0),
                            term_id=source,
                        )
                    if target not in subgraph:
                        subgraph.add_node(
                            target,
                            name=get_term_name(target),
                            count=term_counts.get(target, 0),
                            term_id=target,
                        )

                    subgraph.add_edge(source, target)
            except nx.NetworkXNoPath:
                print(f"No path from {term_id} to root node {root_node}")

    # Add the root node if not already in the graph
    if root_node not in subgraph:
        subgraph.add_node(
            root_node,
            name=get_term_name(root_node),
            count=term_counts.get(root_node, 0),
            term_id=root_node,
        )

    # Use Graphviz layout - need to have graphviz installed
    try:
        pos = nx.nx_agraph.graphviz_layout(subgraph, prog="twopi", args="")
    except ImportError:
        print("Graphviz not available, falling back to spring layout")
        pos = nx.spring_layout(subgraph, seed=42, k=2.0, iterations=500)

    # Create edges as lines
    edge_x = []
    edge_y = []
    for edge in subgraph.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.append(x0)
        edge_x.append(x1)
        edge_x.append(None)
        edge_y.append(y0)
        edge_y.append(y1)
        edge_y.append(None)

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        line=dict(width=0.5, color="rgba(150, 150, 150, 0.6)"),
        hoverinfo="none",
        mode="lines",
    )

    # Create nodes
    node_x = []
    node_y = []
    for node in subgraph.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)

    # Get node counts and names for hover text
    node_counts = []
    node_text = []
    node_sizes = []

    # Separate arrays for labels (only for nodes with count > 0)
    label_x = []
    label_y = []
    label_text = []

    for i, node in enumerate(subgraph.nodes()):
        count = subgraph.nodes[node]["count"]
        name = subgraph.nodes[node]["name"]
        term_id = subgraph.nodes[node]["term_id"]

        node_counts.append(count)
        node_text.append(f"{name}<br>{term_id}<br>Count: {count}")

        # Simple scaling for node sizes
        size = min(100, count) if count > 0 else 8
        node_sizes.append(size)

        # Only add labels for nodes with count > 0
        if count > 0:
            label_x.append(node_x[i])
            label_y.append(node_y[i])
            short_name = name if len(name) < 20 else name[:17] + "..."
            label_text.append(f"{short_name}<br>({count})")

    # Create node trace with a small colorbar
    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers",
        hoverinfo="text",
        marker=dict(
            showscale=True,
            colorscale="Jet",
            reversescale=False,
            color=node_counts,
            size=node_sizes,
            colorbar=dict(
                thickness=10,
                title="Count",
                len=0.3,
                y=0.5,
                yanchor="middle",
                outlinewidth=0,
                tickfont=dict(size=8),
                nticks=4,
            ),
            line=dict(width=0.5, color="#888"),
        ),
        text=node_text,
    )

    # Add text labels
    labels_trace = go.Scatter(
        x=label_x,
        y=label_y,
        mode="text",
        text=label_text,
        textposition="bottom center",
        textfont=dict(family="Arial, sans-serif", size=14, color="rgba(0, 0, 0, 0.7)"),
        hoverinfo="none",
    )

    # Create a simple, clean figure
    fig = go.Figure(
        data=[edge_trace, node_trace, labels_trace],
        layout=go.Layout(
            title="HPO Term Network",
            showlegend=False,
            hovermode="closest",
            margin=dict(b=20, l=20, r=20, t=40),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(
                showgrid=False,
                zeroline=False,
                showticklabels=False,
                scaleanchor="x",
                scaleratio=1,
            ),
            paper_bgcolor="white",
            plot_bgcolor="white",
            width=1000,
            height=1000,
        ),
    )

    return fig, subgraph


def process_hpo_data(individuals, threshold=3):
    """
    Process HPO data from individuals and create visualization data.
    
    Args:
        individuals: QuerySet of Individual objects with HPO terms
        threshold: Minimum count threshold for consolidation
        
    Returns:
        tuple: (consolidated_counts, graph, hpo) for visualization
    """
    # Load HPO ontology
    graph, hpo = load_hpo_ontology()
    
    # Create a dictionary of sample_id -> list of HPO terms
    sample_terms = {}
    for individual in individuals:
        terms = [term.term for term in individual.hpo_terms.all()]
        if terms:  # Only include if there are terms
            sample_terms[individual.individual_id] = terms

    # Count terms
    term_counts = {}
    for sample_id, terms in sample_terms.items():
        for term in terms:
            if term in term_counts:
                term_counts[term] += 1
            else:
                term_counts[term] = 1

    # Consolidate terms for better visualization
    consolidated_counts = consolidate_terms(graph, term_counts, threshold=threshold)
    
    return consolidated_counts, graph, hpo
