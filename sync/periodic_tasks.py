from celery import shared_task
from django.core.management import call_command
from django_celery_beat.models import PeriodicTask, CrontabSchedule
from django.utils import timezone

@shared_task(name='sync.run_sync_script')
def run_sync_script():
    call_command('runscript', 'sync')

def setup_periodic_tasks():
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute='0',
        hour='0',
        day_of_week='*',
        day_of_month='*',
        month_of_year='*',
    )
    PeriodicTask.objects.get_or_create(
        name='Run sync script daily at midnight',
        task='sync.run_sync_script',
        crontab=schedule,
        enabled=True,
    )