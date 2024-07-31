from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django_celery_beat.models import PeriodicTask, CrontabSchedule

@receiver(post_migrate)
def create_periodic_tasks(sender, **kwargs):
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute='0',
        hour='0',
        day_of_week='*',
        day_of_month='*',
        month_of_year='*',
    )
    PeriodicTask.objects.update_or_create(
        name='Run sync script daily at midnight',
        defaults={
            'task': 'sync.run_sync_script',
            'crontab': schedule,
            'enabled': True,
        }
    )

    debug_schedule, _ = CrontabSchedule.objects.get_or_create(
        minute='*/5',
        hour='*',
        day_of_week='*',
        day_of_month='*',
        month_of_year='*',
    )
    PeriodicTask.objects.update_or_create(
        name='Run debug task every 5 minutes',
        defaults={
            'task': 'hltools.celery_app.debug_task',
            'crontab': debug_schedule,
            'enabled': True,
        }
    )
