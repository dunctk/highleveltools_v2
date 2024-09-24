#!/bin/bash


# Run migrations
python manage.py migrate

# Ensure default admin user exists
python manage.py ensure_admin_user

# Migrate Celery Beat database
python manage.py migrate django_celery_beat

# Collect static files
python manage.py collectstatic --no-input

# Create schedules
python manage.py runscript scheduler

# Start the Django development server in the background
python manage.py runserver 8000 &

# Start Celery worker
celery -A hltools worker -l info &

# Start Celery beat
celery -A hltools beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler &

# Wait for all background processes
wait
