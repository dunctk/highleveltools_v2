#!/bin/bash

# Run migrations
python manage.py migrate

# Ensure default admin user exists
python manage.py ensure_admin_user

# Set up cron job
echo "0 10 * * * /usr/local/bin/python /app/manage.py runscript sync" | crontab -

# Start cron service
service cron start

# Start Gunicorn
gunicorn --bind=0.0.0.0:80 --timeout 600 --workers=4 --chdir highleveltools highleveltools.wsgi --access-logfile '-' --error-logfile '-'