from django_q.tasks import schedule
from django_q.models import Schedule, Task
from django_q.brokers import get_broker

def create_schedules():
    # Check if the schedule already exists
    existing_schedule = Schedule.objects.filter(name='sync_process').first()
    
    if not existing_schedule:
        # Create the schedule only if it doesn't exist
        schedule(
            'sync.scripts.sync.run',
            schedule_type=Schedule.DAILY,
            repeats=-1,
            name='sync_process',
        )
        print("Sync process schedule created successfully")
    else:
        print("Sync process schedule already exists")

    # Optionally, clear completed tasks and purge the queue
    Task.objects.filter(success=True).delete()
    broker = get_broker()
    broker.purge_queue()

def run():
    create_schedules()

if __name__ == '__main__':
    run()
