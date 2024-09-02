from django.shortcuts import render
from sync.models import SyncLog

# Create your views here.

def home(request):
    sync_logs = SyncLog.objects.all().order_by('-start_time')  # Order by start time, most recent first
    return render(request, 'sync/home.html', {'sync_logs': sync_logs})
