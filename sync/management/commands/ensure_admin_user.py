from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = 'Ensures that a default admin user exists'

    def handle(self, *args, **options):
        User = get_user_model()
        if not User.objects.filter(username='dunc').exists():
            User.objects.create_superuser('dunc', 'd@uncan.net', 'maple3264')
            self.stdout.write(self.style.SUCCESS('Successfully created default admin user'))
        else:
            self.stdout.write(self.style.SUCCESS('Default admin user already exists'))
