import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hltools.settings')

app = Celery('hltools')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

def setup_periodic_tasks(**kwargs):
    from sync.periodic_tasks import setup_periodic_tasks as setup_sync_tasks
    setup_sync_tasks(app)

app.on_configure.connect(setup_periodic_tasks)