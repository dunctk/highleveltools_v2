from django.contrib import admin
from django.core.management import call_command
from django.contrib import messages
from django.apps import apps

@admin.action(description="Run sync script")
def run_sync_script(modeladmin, request, queryset):
    try:
        call_command('runscript', 'sync')
        messages.success(request, "Sync script ran successfully")
    except Exception as e:
        messages.error(request, f"Error running sync script: {str(e)}")

# Get all models from the current app
models = apps.get_app_config('sync').get_models()

# Register all models and add the run_sync_script action
for model in models:
    @admin.register(model)
    class ModelAdmin(admin.ModelAdmin):
        actions = [run_sync_script]

# Remove the specific PipeLine registration
# @admin.register(PipeLine)
# class YourModelAdmin(admin.ModelAdmin):
#     actions = [run_sync_script]