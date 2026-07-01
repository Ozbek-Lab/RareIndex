from django.conf import settings

# Day-first formats for generic English UI, matching Turkish
# conventions (DD/MM/YYYY).
DATE_FORMAT = getattr(settings, "DATE_FORMAT", "d/m/Y")
TIME_FORMAT = "H:i"
DATETIME_FORMAT = getattr(settings, "DATETIME_FORMAT", "d/m/Y H:i")

SHORT_DATE_FORMAT = getattr(settings, "SHORT_DATE_FORMAT", "d/m/Y")
SHORT_DATETIME_FORMAT = getattr(settings, "SHORT_DATETIME_FORMAT", "d/m/Y H:i")

