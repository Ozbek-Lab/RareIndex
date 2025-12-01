"""
SQLite-specific settings for local development
This module imports the base settings but overrides the database configuration
"""

import os
import sys
from pathlib import Path

# Add the project directory to the path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Import the original settings
from rareindex.settings import *

# Override the database configuration to use SQLite
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "rareindexlite.db",
    }
}

# Override other settings for local development
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
SECRET_KEY = "django-insecure-local-development-key-change-in-production"
# Proper Fernet key for encrypted_model_fields (32 bytes base64 encoded)
FIELD_ENCRYPTION_KEY = "8zAjfdUvXZcoLPvyHAYvap3YD4z3x4QFj0Y6mFODoSo="


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "lab.middleware.CurrentUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",  # For django-allauth 0.54.0+
    "simple_history.middleware.HistoryRequestMiddleware",
    "reversion.middleware.RevisionMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]