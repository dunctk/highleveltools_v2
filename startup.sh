#!/bin/bash

# Change to the project directory
cd /app/hltools


# Conditionally start services based on APP_ENV variable
if [ "$APP_ENV" = 'web' ]; then
    # Run migrations
    python manage.py migrate

    # Ensure default admin user exists
    python manage.py ensure_admin_user
    python manage.py migrate django_celery_beat
    #python manage.py djstripe_sync_models
    python manage.py collectstatic --no-input
    gunicorn --bind=0.0.0.0:80 --timeout 600 --workers=4 --chdir hltools hltools.wsgi --access-logfile '-' --error-logfile '-'
elif [ "$APP_ENV" = 'worker' ]; then
    celery -A hltools worker -l info 
elif [ "$APP_ENV" = 'beat' ]; then
    celery -A hltools beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
fi

 