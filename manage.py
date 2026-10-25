#!/usr/bin/env python3
"""Django management entry point for the PostgreSQL application and backoffice."""
import os
import sys

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backoffice.settings')
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
