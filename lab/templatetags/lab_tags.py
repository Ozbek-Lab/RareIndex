import os
from django import template

register = template.Library()

@register.filter
def get_list(dictionary, key):
    if hasattr(dictionary, 'getlist'):
        return dictionary.getlist(key)
    return dictionary.get(key, [])

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter
def visible_to(notes, user):
    """Filter notes visible to the user"""
    if not user.is_authenticated:
        return []
    
    # Handle related manager or list
    if hasattr(notes, 'all'):
        queryset = notes.all()
    else:
        queryset = notes
        
    filtered = []
    for note in queryset:
        if not note.private_owner or note.private_owner == user:
            filtered.append(note)
    return filtered


@register.simple_tag
def get_statuses(obj):
    """Fetch available statuses for an object's ContentType"""
    from django.contrib.contenttypes.models import ContentType
    from lab.models import Status
    
    ct = ContentType.objects.get_for_model(obj)
    # Exclusively return statuses specific to this content type
    return Status.objects.filter(content_type=ct).order_by('name')

@register.simple_tag(takes_context=True)
def clean_pagination_url(context, page):
    """
    Generates a clean URL for pagination, ensuring 'direction' is removed 
    and other parameters are not duplicated.
    """
    request = context.get('request')
    if not request:
        return f"?page={page}"
    
    query_params = request.GET.copy()
    query_params['page'] = page
    
    # Remove 'direction' if it exists
    if 'direction' in query_params:
        del query_params['direction']
        
    return f"?{query_params.urlencode()}"

@register.simple_tag
def get_content_type_id(obj):
    """Get ContentType ID for an object"""
    from django.contrib.contenttypes.models import ContentType
    return ContentType.objects.get_for_model(obj).id

@register.filter
def class_name(obj):
    return obj.__class__.__name__

@register.filter
def basename(value):
    return os.path.basename(value)
