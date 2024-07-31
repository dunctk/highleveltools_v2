from django.apps import AppConfig
from django.db.models.signals import post_migrate

class SyncConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sync'

    def ready(self):
        from django.conf import settings
        if settings.CELERY_BEAT_SCHEDULER == 'django_celery_beat.schedulers:DatabaseScheduler':
            post_migrate.connect(self._create_periodic_tasks, sender=self)

    def _create_periodic_tasks(self, sender, **kwargs):
        from .periodic_tasks import setup_periodic_tasks
        setup_periodic_tasks()