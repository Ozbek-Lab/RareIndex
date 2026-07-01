INSTITUTION_DISPLAY_NAME = "name"
INSTITUTION_DISPLAY_OFFICIAL_NAME = "official_name"

INSTITUTION_DISPLAY_OPTIONS = [
    {
        "value": INSTITUTION_DISPLAY_NAME,
        "label": "Name",
        "description": "Use the short institution name.",
    },
    {
        "value": INSTITUTION_DISPLAY_OFFICIAL_NAME,
        "label": "Official Name",
        "description": "Use the official institution name when available.",
    },
]

INSTITUTION_DISPLAY_VALUES = {option["value"] for option in INSTITUTION_DISPLAY_OPTIONS}
DEFAULT_INSTITUTION_DISPLAY = INSTITUTION_DISPLAY_NAME


def normalize_institution_display(value):
    if value in INSTITUTION_DISPLAY_VALUES:
        return value
    return DEFAULT_INSTITUTION_DISPLAY


def institution_display_name(institution, mode=DEFAULT_INSTITUTION_DISPLAY):
    mode = normalize_institution_display(mode)
    if institution is None:
        return ""
    if mode == INSTITUTION_DISPLAY_OFFICIAL_NAME:
        return institution.official_name or institution.name or ""
    return institution.name or institution.official_name or ""
