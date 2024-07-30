from django.apps import AppConfig


class SyncConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sync'

    def ready(self):
        from .periodic_tasks import setup_periodic_tasks
        setup_periodic_tasks()