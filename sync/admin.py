from django.contrib import admin
from django.core.management import call_command
from django.contrib import messages
from django.urls import path
from django.shortcuts import redirect
from django_q.tasks import async_task
from .models import PipeLine, SyncLog
from sync.scripts.sync import run  # Add this import at the top of the file

@admin.action(description="Run sync script")
def run_sync_script(modeladmin, request, queryset):
    try:
        call_command('runscript', 'sync')
        messages.success(request, "Sync script ran successfully")
    except Exception as e:
        messages.error(request, f"Error running sync script: {str(e)}")

# Add this action to any of your model admins, for example:
@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ['start_time', 'end_time', 'contacts_attempted', 'contacts_synced', 'status']
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('run-sync-script/', self.admin_site.admin_view(self.run_sync_script_view), name='run-sync-script'),
        ]
        return custom_urls + urls
    
    def run_sync_script_view(self, request):
        # Schedule the task
        task = run.delay()
        messages.success(request, f"Sync script scheduled (Task ID: {task.id})")
        return redirect('admin:sync_synclog_changelist')
    
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_sync_button'] = True
        return super().changelist_view(request, extra_context=extra_context)

# You can keep the PipeLine admin if needed
@admin.register(PipeLine)
class PipeLineAdmin(admin.ModelAdmin):
    actions = [run_sync_script]