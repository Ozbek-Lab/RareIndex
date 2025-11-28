from django import template

register = template.Library()

@register.filter
def get_annotation_data(variant, key):
    """Safely get data from the first annotation of a variant."""
    if not variant:
        return None
    
    # Try to get from prefetch cache or DB
    if hasattr(variant, 'annotations'):
        # If prefetch_related was used, .all() uses cache
        annotations = variant.annotations.all()
        if annotations:
            data = annotations[0].data
            if isinstance(data, dict):
                return data.get(key)
    
    return None
