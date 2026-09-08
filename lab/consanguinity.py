"""Family consanguinity choices and compatibility with legacy boolean values."""

CONSANGUINITY_CHOICES = [
    ("false", "Non-Consanguineous"),
    (None, "Unknown"),
    ("true", "Consanguineous"),
    ("same_village", "Same Village"),
    ("nearby_villages", "Nearby Villages"),
]
CONSANGUINITY_FORM_CHOICES = [(value or "", label) for value, label in CONSANGUINITY_CHOICES]
CONSANGUINITY_FILTER_CHOICES = [(value or "unknown", label) for value, label in CONSANGUINITY_CHOICES]


def normalize_consanguinity(value):
    if value is None or value == "":
        return None
    return str(value).strip().lower() or None
