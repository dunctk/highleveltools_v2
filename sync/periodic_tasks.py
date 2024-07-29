from celery import shared_task
from django.core.management import call_command
from celery.schedules import crontab
from django_celery_beat.models import PeriodicTask, CrontabSchedule

@shared_task
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
        name='Run sync script hourly',
        task='sync.periodic_tasks.run_sync_script',
        crontab=schedule,
    )

# Call this function somewhere in your app's initialization
# setup_periodic_tasks()