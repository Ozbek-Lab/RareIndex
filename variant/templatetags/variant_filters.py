from django import template

register = template.Library()

@register.filter
def get_annotation_data(variant, key):
    """
    Safely get data from the first annotation of a variant.
    Supports dot notation for nested keys (e.g. 'clinvar.hgvs.coding').
    Also supports 'smart' keys like 'hgvsc', 'hgvsp', 'gene' that try multiple sources.
    """
    if not variant:
        return None
    
    # Try to get from prefetch cache or DB
    annotations = None
    if hasattr(variant, 'annotations'):
        # If prefetch_related was used, .all() uses cache
        annotations = variant.annotations.all()
    
    if not annotations:
        return None
        
    # Helper to traverse nested dictionary with dot notation
    def get_nested(data, path):
        parts = path.split('.')
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                # If it's a list, try to find the key in any of the items
                # We prioritize the first non-None match
                found = None
                for item in current:
                    if isinstance(item, dict):
                        val = item.get(part)
                        if val:
                            found = val
                            break
                current = found
            else:
                return None
            
            if current is None:
                return None
        return current

    # Define smart lookup paths for common fields
    smart_paths = {
        'hgvsc': [
            'clinvar.hgvs.coding',
            'snpeff.ann.hgvs_c', 
            'hgvsc', # VEP top level
            'transcript_consequences.hgvsc', # VEP nested
            'myvariant.hgvs.coding'
        ],
        'hgvsp': [
            'clinvar.hgvs.protein',
            'snpeff.ann.hgvs_p',
            'hgvsp', # VEP top level
            'transcript_consequences.hgvsp', # VEP nested
            'myvariant.hgvs.protein'
        ],
        'gene': [
            'clinvar.gene.symbol',
            'snpeff.ann.genename',
            'symbol', # VEP top level
            'transcript_consequences.gene_symbol', # VEP nested
            'transcript_consequences.hgnc_id', # VEP nested fallback
            'transcript_consequences.gene_id', # VEP nested fallback (Ensembl ID)
            'myvariant.gene.symbol'
        ]
    }

    # Determine paths to check
    paths_to_check = smart_paths.get(key, [key])

    # Iterate through annotations and paths
    for annotation in annotations:
        data_items = annotation.data
        if isinstance(data_items, dict):
            data_items = [data_items]
        elif not isinstance(data_items, list):
            continue
            
        for data in data_items:
            if not isinstance(data, dict):
                continue
                
            for path in paths_to_check:
                value = get_nested(data, path)
                if value:
                    return value
                
    return None
