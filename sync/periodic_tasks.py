from celery import shared_task
from django.core.management import call_command
from django_celery_beat.models import PeriodicTask, CrontabSchedule
from django.utils import timezone

@shared_task(name='sync.run_sync_script')
def run_sync_script():
    call_command('runscript', 'sync')

# Remove the setup_periodic_tasks function from here