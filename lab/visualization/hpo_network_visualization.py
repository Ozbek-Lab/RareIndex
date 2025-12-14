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


import os
from django.conf import settings
from functools import lru_cache


@lru_cache(maxsize=1)
def load_hpo_ontology():
    """
    Load the HPO ontology from the OBO file and create a NetworkX graph.
    Uses local cache if available, otherwise downloads.
    Keeps the result in memory with lru_cache.
    
    Returns:
        tuple: (graph, hpo) where graph is a NetworkX DiGraph and hpo is the fastobo object
    """
    # Define local path for HPO data
    data_dir = os.path.join(settings.BASE_DIR, 'hpo_data')
    os.makedirs(data_dir, exist_ok=True)
    local_path = os.path.join(data_dir, 'hp.obo')
    
    obo_url = "https://purl.obolibrary.org/obo/hp.obo"
    
    # Download if not exists
    if not os.path.exists(local_path):
        print(f"Downloading HPO ontology from {obo_url}...")
        try:
            with urllib.request.urlopen(obo_url) as response, open(local_path, 'wb') as out_file:
                out_file.write(response.read())
            print("Download complete.")
        except Exception as e:
            print(f"Failed to download HPO ontology: {e}")
            # Fallback to direct download if local save fails, though unlikely
            pass

    graph = nx.DiGraph()

    # Load from local file if exists, else from URL (fallback)
    if os.path.exists(local_path):
        print(f"Loading HPO ontology from {local_path}...")
        hpo = fastobo.load(local_path)
    else:
        print(f"Loading HPO ontology from {obo_url} (fallback)...")
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
    Consolidate rare HPO terms by moving their individuals to their parents.
    
    Args:
        graph: NetworkX graph of HPO terms
        terms: Dictionary of term_id -> set of individual_ids
        threshold: Minimum count threshold for consolidation
        
    Returns:
        dict: Consolidated term dictionary (term_id -> set of individual_ids)
    """
    # Create a working copy of the dictionary
    working_terms = {k: v.copy() for k, v in terms.items()}
    root_node = "HP:0000118"  # Phenotypic abnormality

    # Check if all terms exist in the graph, remove those that don't
    invalid_terms = []
    for term in working_terms:
        if term not in graph:
            warnings.warn(
                f"The node {term} is not in the graph. Removing from consolidation."
            )
            invalid_terms.append(term)

    for term in invalid_terms:
        working_terms.pop(term, None)

    # Continue until we can't consolidate further
    while True:
        # Get all current terms that are below threshold
        rare_terms = [
            term for term, individuals in working_terms.items() if len(individuals) < threshold
        ]
        
        # If no rare terms, we are done
        if not rare_terms:
            break
            
        changes_made = False
        
        for term in rare_terms:
            # Don't consolidate the root itself
            if term == root_node:
                continue
                
            try:
                # Find path to root to get the immediate parent
                path = nx.shortest_path(graph, term, root_node)
                if len(path) > 1:
                    parent = path[1] # path[0] is term, path[1] is parent
                    
                    # Move individuals to parent
                    individuals = working_terms.pop(term)
                    if parent in working_terms:
                        working_terms[parent].update(individuals)
                    else:
                        working_terms[parent] = individuals
                        
                    changes_made = True
            except (nx.NetworkXNoPath, IndexError):
                # Cannot reach root or no parent, skip
                continue
                
        # If we went through all rare terms and made no changes, we are stuck
        if not changes_made:
            break

    return working_terms


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


def plotly_hpo_network(graph, hpo, term_individuals, output_file=None, min_count=1):
    """
    Create a Plotly network visualization of HPO terms.
    
    Args:
        graph: NetworkX graph of HPO terms
        hpo: Fastobo HPO object
        term_individuals: Dictionary of term_id -> set of individual_ids
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
    for term_id, individuals in term_individuals.items():
        count = len(individuals)
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
            subgraph.add_node(term_id, name=name, count=count, term_id=term_id, individuals=list(individuals))

            # Add path from this term to the root node
            try:
                path = nx.shortest_path(graph, term_id, root_node)
                for i in range(len(path) - 1):
                    source = path[i]
                    target = path[i + 1]

                    if source not in subgraph:
                        source_individuals = term_individuals.get(source, set())
                        subgraph.add_node(
                            source,
                            name=get_term_name(source),
                            count=len(source_individuals),
                            term_id=source,
                            individuals=list(source_individuals)
                        )
                    if target not in subgraph:
                        target_individuals = term_individuals.get(target, set())
                        subgraph.add_node(
                            target,
                            name=get_term_name(target),
                            count=len(target_individuals),
                            term_id=target,
                            individuals=list(target_individuals)
                        )

                    subgraph.add_edge(source, target)
            except nx.NetworkXNoPath:
                print(f"No path from {term_id} to root node {root_node}")

    # Add the root node if not already in the graph
    if root_node not in subgraph:
        root_individuals = term_individuals.get(root_node, set())
        subgraph.add_node(
            root_node,
            name=get_term_name(root_node),
            count=len(root_individuals),
            term_id=root_node,
            individuals=list(root_individuals)
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


def process_hpo_data(individuals, threshold=12):
    """
    Process HPO data from individuals and create visualization data.
    
    Args:
        individuals: QuerySet of Individual objects with HPO terms
        threshold: Minimum count threshold for consolidation
        
    Returns:
        tuple: (consolidated_terms, graph, hpo) for visualization
        consolidated_terms: dict of term_id -> set of individual_ids
    """
    # Load HPO ontology
    graph, hpo = load_hpo_ontology()
    
    # Map term -> set of (pk, individual_id) tuples
    term_individuals = {}
    
    for individual in individuals:
        terms = [term.term for term in individual.hpo_terms.all()]
        # Pre-fetch individual_id to avoid N+1 if not already selected, 
        # though individual_id property might hit DB if cross_ids not prefetched.
        # Assuming acceptable for now or handled by view.
        ind_data = (individual.pk, individual.individual_id)
        
        for term in terms:
            if term not in term_individuals:
                term_individuals[term] = set()
            term_individuals[term].add(ind_data)

    # Consolidate terms for better visualization
    consolidated_terms = consolidate_terms(graph, term_individuals, threshold=threshold)
    
    return consolidated_terms, graph, hpo


def cytoscape_hpo_network(graph, hpo, term_individuals, min_count=1):
    """
    Build Cytoscape.js elements for an HPO network from term individuals.
    
    Args:
        graph: NetworkX graph of HPO terms
        hpo: Fastobo HPO object
        term_individuals: Dictionary of term_id -> set of individual_ids
        min_count: Minimum count threshold for displaying terms
        
    Returns:
        tuple: (elements, subgraph) where elements is a list of Cytoscape.js
               node/edge dicts suitable for JSON serialization, and subgraph is
               the NetworkX subgraph that was constructed.
    """
    # Function to extract term name from the HPO ontology
    def get_term_name(term_id):
        for frame in hpo:
            if isinstance(frame, fastobo.term.TermFrame) and str(frame.id) == term_id:
                for clause in frame:
                    if isinstance(clause, fastobo.term.NameClause):
                        return str(clause.name)
        return term_id

    root_node = "HP:0000118"  # Phenotypic abnormality

    # Create a subgraph with terms and paths to root (same logic as Plotly pathing)
    subgraph = nx.DiGraph()

    for term_id, individuals in term_individuals.items():
        count = len(individuals)
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

            subgraph.add_node(term_id, name=name, count=count, term_id=term_id, individuals=list(individuals))

            try:
                path = nx.shortest_path(graph, term_id, root_node)
                for i in range(len(path) - 1):
                    source = path[i]
                    target = path[i + 1]

                    if source not in subgraph:
                        source_individuals = term_individuals.get(source, set())
                        subgraph.add_node(
                            source,
                            name=get_term_name(source),
                            count=len(source_individuals),
                            term_id=source,
                            individuals=list(source_individuals)
                        )
                    if target not in subgraph:
                        target_individuals = term_individuals.get(target, set())
                        subgraph.add_node(
                            target,
                            name=get_term_name(target),
                            count=len(target_individuals),
                            term_id=target,
                            individuals=list(target_individuals)
                        )

                    subgraph.add_edge(source, target)
            except nx.NetworkXNoPath:
                print(f"No path from {term_id} to root node {root_node}")

    if root_node not in subgraph:
        root_individuals = term_individuals.get(root_node, set())
        subgraph.add_node(
            root_node,
            name=get_term_name(root_node),
            count=len(root_individuals),
            term_id=root_node,
            individuals=list(root_individuals)
        )

    # Build Cytoscape.js elements: nodes and edges (positions handled client-side by Cytoscape layouts)
    elements = []

    for node_id, data in subgraph.nodes(data=True):
        # Convert list of (pk, id) tuples to list of dicts for JSON serialization
        individuals_data = []
        if "individuals" in data:
            for ind in data["individuals"]:
                # Check if it's a tuple (pk, id) or just pk (backward compatibility)
                if isinstance(ind, tuple) and len(ind) == 2:
                    individuals_data.append({"pk": ind[0], "display_id": ind[1]})
                else:
                     individuals_data.append({"pk": ind, "display_id": f"Individual {ind}"})
        
        elements.append(
            {
                "data": {
                    "id": node_id,
                    "label": data.get("name", node_id),
                    "count": int(data.get("count", 0)),
                    "term_id": data.get("term_id", node_id),
                    "individuals": individuals_data,
                }
            }
        )

    for source, target in subgraph.edges():
        elements.append(
            {
                "data": {
                    "id": f"{source}->{target}",
                    "source": source,
                    "target": target,
                }
            }
        )


    return elements, subgraph


def cytoscape_elements_json(elements):
    """
    Serialize Cytoscape.js elements to a JSON string for embedding in templates.
    """
    return json.dumps(elements)
