import os
import urllib.request
import fastobo
import networkx as nx
from django.conf import settings
from functools import lru_cache
from collections import defaultdict
from django.core.cache import cache
from .models import Term

HBO_URL = "https://purl.obolibrary.org/obo/hp.obo"
ONTOLOGY_DIR = os.path.join(settings.MEDIA_ROOT, 'ontologies')
OBO_PATH = os.path.join(ONTOLOGY_DIR, 'hp.obo')

# get_global_hpo_tree removed as part of HPO optimization

OBO_PATH = os.path.join(ONTOLOGY_DIR, 'hp.obo')

@lru_cache(maxsize=1)
def load_hpo_graph():
    """
    Load HPO ontology into a NetworkX DiGraph.
    Caches the graph in memory.
    Downloads the .obo file if not present locally.
    """
    # Ensure directory exists
    os.makedirs(ONTOLOGY_DIR, exist_ok=True)
    
    # Download if missing
    if not os.path.exists(OBO_PATH):
        print(f"Downloading HPO ontology from {HBO_URL}...")
        try:
            with urllib.request.urlopen(HBO_URL) as response, open(OBO_PATH, 'wb') as out_file:
                out_file.write(response.read())
        except Exception as e:
            # Cleanup partial download
            if os.path.exists(OBO_PATH):
                os.remove(OBO_PATH)
            raise e

    # Load with fastobo
    graph = nx.DiGraph()
    
    # Identify is_a edges
    # fastobo.load returns an iterator over frames
    # We iterate twice? No, fastobo.load returns a Doc which is iterable?
    # Actually fastobo.load takes a file-like object or path.
    # fastobo.load(path) is better if passing path string.
    
    doc = fastobo.load(OBO_PATH)
    
    # We only care about Term frames
    for frame in doc:
        if isinstance(frame, fastobo.term.TermFrame):
            term_id = str(frame.id)
            name = str(frame.id) # Default fallback
            
            # Extract name
            for clause in frame:
                if isinstance(clause, fastobo.term.NameClause):
                    name = str(clause.name)
                    break
            
            graph.add_node(term_id, name=name)
            
            for clause in frame:
                if isinstance(clause, fastobo.term.IsAClause):
                    parent_id = str(clause.term)
                    # Edge: Parent -> Child for intuitive top-down traversal (reverse is_a)
                    graph.add_edge(parent_id, term_id)
                    
    return graph

def get_hpo_tree(used_term_ids):
    """
    Builds a tree structure of HPO terms given a list of used IDs.
    Uses NetworkX graph to find full ancestry.
    """
    if not used_term_ids:
        return []

    graph = load_hpo_graph()
    
    # Set of interest: used IDs + all their ancestors
    # Ancestors in our Parent->Child graph correspond to nodes that can reach the used ID?
    # Wait, if edges are Parent -> Child:
    # Ancestors of X are nodes that have path TO X.
    # nx.ancestors(G, source) returns all nodes having a path to source.
    # So yes, ancestors(child) -> parents.
    
    relevant_ids = set()
    cleaned_used_ids = set()
    
    # Resolve numeric/string IDs
    # Our DB stores IDs often without prefix "HP:", or maybe with? 
    # Term.identifier stores "0000118".
    # OBO file uses "HP:0000118".
    # We need a mapping/helper.
    # Assuming DB Term.identifier is just digits, lets check models.
    # Term.term property returns f'HP:{self.identifier}'.
    # So we should convert DB IDs to OBO IDs ("HP:" + id) for graph lookup.
    
    # Fetch DB objects for used IDs to get correct identifiers
    if not used_term_ids:
         return []
         
    # used_term_ids might be IDs (PKs) or strings?
    # The view passes used_ids which are Term PKs? No, values_list('hpo_terms', flat=True) -> Term PKs.
    # We need to get the actual Term objects to get the identifier.
    
    used_db_terms = Term.objects.filter(id__in=used_term_ids)
    
    # Map DB ID -> OBO ID
    db_id_to_obo = {t.id: t.term for t in used_db_terms} # t.term is "HP:00123"
    obo_to_db_term = {t.term: t for t in used_db_terms}
    
    # Set of OBO IDs we want
    target_obo_ids = set(db_id_to_obo.values())
    
    final_obo_ids = set()
    
    for obo_id in target_obo_ids:
        if obo_id in graph:
            final_obo_ids.add(obo_id)
            # Add ancestors (nodes strictly above)
            final_obo_ids.update(nx.ancestors(graph, obo_id))
        else:
            # Term might be obsolete or missing from OBO
            print(f"Warning: Term {obo_id} not found in HPO graph.")
            # Add it anyway? No, can't structure it.
            # But we should show it if it's used.
            # Maybe show as root?
            final_obo_ids.add(obo_id)

    # Now we have a set of OBO IDs (strings like "HP:000123")
    # We need to fetch/create Term objects for them to pass to template.
    # The DB might not have all ancestors. We might need to construct dummy objects or
    # rely on what's in DB.
    # Requirement: "Show in hierarchical order".
    # Ideally we use DB terms.
    # If ancestor not in DB, we can't show label easily without parsing OBO labels (fastobo provides names).
    # Refactor: load_hpo_graph should ideally return frame map or we re-read names?
    # fastobo loads names. We can store them in graph nodes.
    
    # Let's verify if we need to show labels for ancestors not in DB.
    # Probably yes.
    # Let's update load_hpo_graph to store attributes.
    
    # For now, let's assume we only strictly need what's in DB + structure?
    # If an ancestor is missing from DB, we can't link the tree visually unless we show a placeholder.
    # Better: Ensure DB is synced? No, that's a separate task.
    # We should render the tree using OBO data primarily for structure/labels, 
    # and mark "used" ones based on DB selection.
    
    # Let's refine the node builder.
    
    # Subgraph for the view
    subgraph = graph.subgraph(final_obo_ids)
    
    # Root nodes in subgraph: in_degree 0
    roots = [n for n in subgraph.nodes() if subgraph.in_degree(n) == 0]
    
    # Helper to get label
    # We can fetch labels from DB for existing ones, and OBO for others?
    # Assuming fastobo didn't save labels in graph, we might want to.
    
    # Re-loading graph with labels is expensive.
    # Let's try to fetch all corresponding Terms from DB first.
    # We need to look up by identifier (strip "HP:").
    
    all_identifiers = [oid.split(':')[1] for oid in final_obo_ids if ':' in oid]
    db_terms = Term.objects.filter(identifier__in=all_identifiers, ontology__type=1) # 1=HP
    obo_id_to_db_term = {t.term: t for t in db_terms}
    
    def get_node_label(obo_id):
        if obo_id in obo_id_to_db_term:
            return obo_id_to_db_term[obo_id].label
        # Fallback to OBO label? 
        # We need to store it in graph or reload.
        # Let's update load_hpo_graph to store name.
        if 'name' in graph.nodes[obo_id]:
             return graph.nodes[obo_id]['name']
        return obo_id

    def build_node(obo_id):
        db_term = obo_id_to_db_term.get(obo_id)
        is_used = db_term and db_term.id in db_id_to_obo # Check if this DB term ID was in input
        
        node = {
            'id': db_term.id if db_term else obo_id, # Value for checkbox. If no DB ID, can't select?
            'label': get_node_label(obo_id),
            'identifier': obo_id,
            'term': db_term,
            'is_used': bool(is_used),
            'children': [],
            # If no DB term, we can't filter by it backend-wise easily unless we pass OBO ID.
            # The filter expects Term IDs.
            # If intermediate node is not in DB, user can't select it? 
            # Or we disable checkbox.
            'selectable': bool(db_term) 
        }
        
        children = sorted([n for n in subgraph.successors(obo_id)], key=lambda x: get_node_label(x))
        node['children'] = [build_node(child) for child in children]
        return node
        
    tree = [build_node(root) for root in sorted(roots, key=lambda x: get_node_label(x))]
    return tree

def get_descendants(term_ids):
    """
    Returns a set of all descendant term IDs (DB PKs) for the given term IDs (DB PKs).
    """
    if not term_ids:
        return set()
        
    graph = load_hpo_graph()
    
    # Convert DB PKs to OBO IDs
    terms = Term.objects.filter(id__in=term_ids)
    obo_ids = [t.term for t in terms]
    
    all_descendants_obo = set(obo_ids)
    for oid in obo_ids:
        if oid in graph:
            all_descendants_obo.update(nx.descendants(graph, oid))
            
    # Convert back to DB PKs
    # Extract identifiers
    identifiers = [oid.split(':')[1] for oid in all_descendants_obo if ':' in oid]
    return Term.objects.filter(identifier__in=identifiers, ontology__type=1).values_list('id', flat=True)

def get_descendants_from_obo(obo_ids):
    """
    Given a list of OBO IDs (e.g. ['HP:0001250']), return a set of all descendant term IDs (DB PKs).
    """
    if not obo_ids:
        return set()
        
    graph = load_hpo_graph()
    
    all_descendants_obo = set(obo_ids)
    for oid in obo_ids:
        if oid in graph:
            all_descendants_obo.update(nx.descendants(graph, oid))
            
    # Convert back to DB PKs
    identifiers = [oid.split(':')[1] for oid in all_descendants_obo if ':' in oid]
    return Term.objects.filter(identifier__in=identifiers, ontology__type=1).values_list('id', flat=True)
