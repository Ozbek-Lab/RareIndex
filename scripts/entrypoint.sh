#!/bin/sh

# Exit immediately if a command exits with a non-zero status
set -e

# Apply database migrations
echo "Applying database migrations..."
python manage.py makemigrations
python manage.py makemigrations lab
python manage.py migrate

# Collect static files
echo "Downloading frontend vendor assets..."
python scripts/download_static_vendor.py

echo "Collecting static files..."
python manage.py collectstatic --no-input

gunicorn \
    rareindex.wsgi:application \
    --bind 0.0.0.0:8090 \
    --log-level debug \
    --access-logfile '-' \
    --error-logfile '-' \
    --workers 2
