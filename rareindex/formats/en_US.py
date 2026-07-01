from django.conf import settings

# Day-first formats for English (US locale code) UI, matching Turkish
# conventions (DD/MM/YYYY). This ensures that LANGUAGE_CODE="en-us"
# picks up these formats via FORMAT_MODULE_PATH.
DATE_FORMAT = getattr(settings, "DATE_FORMAT", "d/m/Y")
TIME_FORMAT = "H:i"
DATETIME_FORMAT = getattr(settings, "DATETIME_FORMAT", "d/m/Y H:i")

SHORT_DATE_FORMAT = getattr(settings, "SHORT_DATE_FORMAT", "d/m/Y")
SHORT_DATETIME_FORMAT = getattr(settings, "SHORT_DATETIME_FORMAT", "d/m/Y H:i")

