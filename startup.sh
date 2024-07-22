#!/bin/bash

# Change to the project directory
cd /app/hltools

# Run migrations
python manage.py migrate

# Ensure default admin user exists
python manage.py ensure_admin_user

# Set up cron job
echo "0 10 * * * cd /app/hltools && /usr/local/bin/python manage.py runscript sync" | crontab -

# Start cron service
service cron start

# Start Gunicorn
gunicorn --bind=0.0.0.0:80 --timeout 600 --workers=4 --chdir hltools hltools.wsgi --access-logfile '-' --error-logfile '-'