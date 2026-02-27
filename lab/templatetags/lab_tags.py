import os
import json
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
def grch_to_hg(value):
    """Convert GRCh38/GRCh37 assembly names to UCSC hg38/hg19 style."""
    return {'GRCh38': 'hg38', 'GRCh37': 'hg19'}.get(str(value), str(value))


@register.filter
def json_pretty(value):
    """Serialize a Python object to an indented JSON string for display."""
    try:
        return json.dumps(value, indent=2, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)

@register.filter
def basename(value):
    return os.path.basename(value)


_CSS_NAMED_COLORS = {
    "aliceblue": "f0f8ff", "antiquewhite": "faebd7", "aqua": "00ffff",
    "aquamarine": "7fffd4", "azure": "f0ffff", "beige": "f5f5dc",
    "bisque": "ffe4c4", "black": "000000", "blanchedalmond": "ffebcd",
    "blue": "0000ff", "blueviolet": "8a2be2", "brown": "a52a2a",
    "burlywood": "deb887", "cadetblue": "5f9ea0", "chartreuse": "7fff00",
    "chocolate": "d2691e", "coral": "ff7f50", "cornflowerblue": "6495ed",
    "cornsilk": "fff8dc", "crimson": "dc143c", "cyan": "00ffff",
    "darkblue": "00008b", "darkcyan": "008b8b", "darkgoldenrod": "b8860b",
    "darkgray": "a9a9a9", "darkgreen": "006400", "darkgrey": "a9a9a9",
    "darkkhaki": "bdb76b", "darkmagenta": "8b008b", "darkolivegreen": "556b2f",
    "darkorange": "ff8c00", "darkorchid": "9932cc", "darkred": "8b0000",
    "darksalmon": "e9967a", "darkseagreen": "8fbc8f", "darkslateblue": "483d8b",
    "darkslategray": "2f4f4f", "darkslategrey": "2f4f4f", "darkturquoise": "00ced1",
    "darkviolet": "9400d3", "deeppink": "ff1493", "deepskyblue": "00bfff",
    "dimgray": "696969", "dimgrey": "696969", "dodgerblue": "1e90ff",
    "firebrick": "b22222", "floralwhite": "fffaf0", "forestgreen": "228b22",
    "fuchsia": "ff00ff", "gainsboro": "dcdcdc", "ghostwhite": "f8f8ff",
    "gold": "ffd700", "goldenrod": "daa520", "gray": "808080",
    "green": "008000", "greenyellow": "adff2f", "grey": "808080",
    "honeydew": "f0fff0", "hotpink": "ff69b4", "indianred": "cd5c5c",
    "indigo": "4b0082", "ivory": "fffff0", "khaki": "f0e68c",
    "lavender": "e6e6fa", "lavenderblush": "fff0f5", "lawngreen": "7cfc00",
    "lemonchiffon": "fffacd", "lightblue": "add8e6", "lightcoral": "f08080",
    "lightcyan": "e0ffff", "lightgoldenrodyellow": "fafad2", "lightgray": "d3d3d3",
    "lightgreen": "90ee90", "lightgrey": "d3d3d3", "lightpink": "ffb6c1",
    "lightsalmon": "ffa07a", "lightseagreen": "20b2aa", "lightskyblue": "87cefa",
    "lightslategray": "778899", "lightslategrey": "778899", "lightsteelblue": "b0c4de",
    "lightyellow": "ffffe0", "lime": "00ff00", "limegreen": "32cd32",
    "linen": "faf0e6", "magenta": "ff00ff", "maroon": "800000",
    "mediumaquamarine": "66cdaa", "mediumblue": "0000cd", "mediumorchid": "ba55d3",
    "mediumpurple": "9370db", "mediumseagreen": "3cb371", "mediumslateblue": "7b68ee",
    "mediumspringgreen": "00fa9a", "mediumturquoise": "48d1cc", "mediumvioletred": "c71585",
    "midnightblue": "191970", "mintcream": "f5fffa", "mistyrose": "ffe4e1",
    "moccasin": "ffe4b5", "navajowhite": "ffdead", "navy": "000080",
    "oldlace": "fdf5e6", "olive": "808000", "olivedrab": "6b8e23",
    "orange": "ffa500", "orangered": "ff4500", "orchid": "da70d6",
    "palegoldenrod": "eee8aa", "palegreen": "98fb98", "paleturquoise": "afeeee",
    "palevioletred": "db7093", "papayawhip": "ffefd5", "peachpuff": "ffdab9",
    "peru": "cd853f", "pink": "ffc0cb", "plum": "dda0dd",
    "powderblue": "b0e0e6", "purple": "800080", "red": "ff0000",
    "rosybrown": "bc8f8f", "royalblue": "4169e1", "saddlebrown": "8b4513",
    "salmon": "fa8072", "sandybrown": "f4a460", "seagreen": "2e8b57",
    "seashell": "fff5ee", "sienna": "a0522d", "silver": "c0c0c0",
    "skyblue": "87ceeb", "slateblue": "6a5acd", "slategray": "708090",
    "slategrey": "708090", "snow": "fffafa", "springgreen": "00ff7f",
    "steelblue": "4682b4", "tan": "d2b48c", "teal": "008080",
    "thistle": "d8bfd8", "tomato": "ff6347", "turquoise": "40e0d0",
    "violet": "ee82ee", "wheat": "f5deb3", "white": "ffffff",
    "whitesmoke": "f5f5f5", "yellow": "ffff00", "yellowgreen": "9acd32",
}


@register.filter
def contrast_color(color):
    """Return 'white' or '#1a1a1a' for readable text over the given background color."""
    if not color:
        return "white"
    raw = color.strip().lower()

    # Resolve CSS named color to hex
    if raw in _CSS_NAMED_COLORS:
        raw = _CSS_NAMED_COLORS[raw]

    raw = raw.lstrip("#")
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    if len(raw) != 6:
        return "white"
    try:
        r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    except ValueError:
        return "white"
    luminance = (r * 299 + g * 587 + b * 114) / 1000
    return "#1a1a1a" if luminance > 150 else "white"
