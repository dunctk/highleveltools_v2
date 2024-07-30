from celery import shared_task
from django.core.management import call_command
from celery.schedules import crontab

@shared_task(name='sync.run_sync_script')
def run_sync_script():
    call_command('runscript', 'sync')

def setup_periodic_tasks(app, **kwargs):
    # Run sync script every day at midnight
    app.add_periodic_task(
        crontab(minute=0, hour=0),
        run_sync_script.s(),
        name='Run sync script daily at midnight'
    )