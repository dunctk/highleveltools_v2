import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hltools.settings')

app = Celery('hltools')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Ensure this import is at the end of the file
from sync.periodic_tasks import setup_periodic_tasks
setup_periodic_tasks(app)