#!/bin/sh

# Exit immediately if a command exits with a non-zero status
set -e

# Apply database migrations
echo "Applying database migrations..."
python manage.py makemigrations
python manage.py migrate

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --no-input

gunicorn \
    rareindex.wsgi:application \
    --bind 0.0.0.0:8000 \
    --log-level debug \
    --access-logfile '-' \
    --error-logfile '-' \
    --workers 2
