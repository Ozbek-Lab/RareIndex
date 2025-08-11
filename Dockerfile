# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
    # for psycopg2
    libpq-dev \
    # for pygraphviz
    graphviz \
    graphviz-dev \
    # for git dependencies
    git \
    # for entrypoint.sh
    netcat-openbsd && \
    apt-get clean

# Create a non-root user
RUN addgroup --system app && adduser --system --group app

# Set workdir
WORKDIR /app

# Install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Use the non-root user
USER app

# Copy project
COPY . /app/

# Expose the port the app runs on
EXPOSE 8000

# Entrypoint command
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "rareindex.wsgi:application"]
