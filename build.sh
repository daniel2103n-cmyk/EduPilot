#!/usr/bin/env bash
# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Convert static assets
python manage.py collectstatic --noinput

# Run migrations
python manage.py migrate

# Create initial database data (superuser and default program)
python -c "
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# 1. Ensure 'Ingeniería de Sistemas' program exists
from apps.academic.models import AcademicProgram
program_name = 'Ingeniería de Sistemas'
if not AcademicProgram.objects.filter(name=program_name).exists():
    AcademicProgram.objects.create(name=program_name, is_active=True)
    print(f'Academic program {program_name} created successfully')
else:
    print(f'Academic program {program_name} already exists')

# 2. Ensure superuser exists
from django.contrib.auth import get_user_model
User = get_user_model()
username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
if username and password:
    if not User.objects.filter(username=username).exists():
        User.objects.create_superuser(username=username, email=email, password=password, role='ADMIN')
        print('Superuser created successfully')
    else:
        print('Superuser already exists')
"
