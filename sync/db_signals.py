from django.db.backends.signals import connection_created
from django.dispatch import receiver

@receiver(connection_created)
def setup_sqlite_pragmas(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        cursor = connection.cursor()
        cursor.execute('PRAGMA journal_mode=wal;')
        cursor.execute('PRAGMA synchronous=NORMAL;')
        cursor.execute('PRAGMA cache_size=-64000;')
        cursor.execute('PRAGMA foreign_keys=ON;')
        cursor.execute('PRAGMA busy_timeout=5000;')
        cursor.close()