import logging
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django_celery_beat.models import PeriodicTask, CrontabSchedule

logger = logging.getLogger(__name__)

@receiver(post_migrate)
def create_periodic_tasks(sender, **kwargs):
    logger.info("Creating periodic tasks...")
    try:
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute='0',
            hour='0',
            day_of_week='*',
            day_of_month='*',
            month_of_year='*',
        )
        task, created = PeriodicTask.objects.update_or_create(
            name='Run sync script daily at midnight',
            defaults={
                'task': 'sync.run_sync_script',
                'crontab': schedule,
                'enabled': True,
            }
        )
        logger.info(f"Sync script task {'created' if created else 'updated'}")

        debug_schedule, _ = CrontabSchedule.objects.get_or_create(
            minute='*/5',
            hour='*',
            day_of_week='*',
            day_of_month='*',
            month_of_year='*',
        )
        debug_task, created = PeriodicTask.objects.update_or_create(
            name='Run debug task every 5 minutes',
            defaults={
                'task': 'hltools.celery_app.debug_task',
                'crontab': debug_schedule,
                'enabled': True,
            }
        )
        logger.info(f"Debug task {'created' if created else 'updated'}")
    except Exception as e:
        logger.error(f"Error creating periodic tasks: {str(e)}")