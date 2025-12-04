# Use an official Python runtime as a parent image
FROM python:3.14-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
    gcc \
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

# Set workdir
WORKDIR /app

# Install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . .
