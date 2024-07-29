from celery import Celery

app = Celery('hltools')

# Load task modules from all registered Django app configs.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# This allows you to run celery -A hltools
celery_app = app