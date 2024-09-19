from django.contrib import admin
from django.core.management import call_command
from django.contrib import messages
from .models import PipeLine

@admin.action(description="Run sync script")
def run_sync_script(modeladmin, request, queryset):
    try:
        call_command('runscript', 'sync')
        messages.success(request, "Sync script ran successfully")
    except Exception as e:
        messages.error(request, f"Error running sync script: {str(e)}")

# Add this action to any of your model admins, for example:
@admin.register(PipeLine)
class YourModelAdmin(admin.ModelAdmin):
    actions = [run_sync_script]