#!/usr/bin/env python
"""
Local development manage.py that uses SQLite settings
This file sets the Django settings module before Django loads anything
"""
import os
import sys
from pathlib import Path

def main():
    """Run administrative tasks."""
    # Set Django settings module BEFORE importing Django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rareindex.settings_sqlite')
    
    # Add the project directory to Python path
    project_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(project_dir))
    
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    
    # Display local development info
    print("🚀 Using local SQLite settings (rareindex.settings_sqlite)")
    print("📁 Database: rareindexlite.db")
    print("⚠️  Local development mode - NOT for production!")
    print("-" * 50)
    
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
