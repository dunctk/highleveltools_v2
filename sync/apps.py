import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)

class SyncConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sync'

    def ready(self):
        logger.info("SyncConfig ready method called")
        import sync.signals  # This imports the signals
        logger.info("Signals imported")