#!/bin/bash

# Change to the project directory
cd /app/hltools

# Debug: Print current directory and list files
echo "Current directory: $(pwd)"
ls -la

# Ensure the database directory exists
mkdir -p /app/hltools/data

# Debug: Check if the database file exists
if [ -f /app/hltools/data/db.sqlite3 ]; then
    echo "Database file exists"
else
    echo "Database file does not exist, creating it"
    touch /app/hltools/data/db.sqlite3
fi

# Run migrations for all environments
python manage.py makemigrations
python manage.py migrate
python manage.py migrate django_celery_beat

# Debug: List tables in the database
echo "Tables in the database:"
sqlite3 /app/hltools/data/db.sqlite3 ".tables"

# Conditionally start services based on APP_ENV variable
if [ "$APP_ENV" = 'web' ]; then
    # Ensure default admin user exists
    python manage.py ensure_admin_user
    #python manage.py djstripe_sync_models
    python manage.py collectstatic --no-input
    gunicorn --bind=0.0.0.0:80 --timeout 600 --workers=4 --chdir hltools hltools.wsgi --access-logfile '-' --error-logfile '-'
elif [ "$APP_ENV" = 'worker' ]; then
    celery -A hltools worker -l info 
elif [ "$APP_ENV" = 'beat' ]; then
    celery -A hltools beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
fi