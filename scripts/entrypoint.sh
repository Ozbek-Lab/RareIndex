#!/bin/sh

# Exit immediately if a command exits with a non-zero status
set -e

# Wait for the database to be ready
# The `DATABASE_HOST` and `DATABASE_PORT` variables will be set in the docker-compose file
echo "Waiting for database..."
while ! nc -z $DATABASE_HOST $DATABASE_PORT; do
  sleep 0.1
done
echo "Database started"

# Export email secrets to environment variables if they exist
if [ -f /run/secrets/email_host_user ]; then
    export EMAIL_HOST_USER=$(cat /run/secrets/email_host_user)
fi
if [ -f /run/secrets/email_host_password ]; then
    export EMAIL_HOST_PASSWORD=$(cat /run/secrets/email_host_password)
fi

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --no-input

# Start Gunicorn server
echo "Starting Gunicorn server..."
exec "$@"
