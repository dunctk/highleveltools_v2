from django_q.tasks import schedule
from django_q.models import Schedule, Task
from django_q.brokers import get_broker

def create_schedules():
    # Delete ALL existing schedules
    Schedule.objects.all().delete()
    
    # Delete all tasks
    Task.objects.all().delete()
    
    # Clear the queue
    broker = get_broker()
    broker.purge_queue()

    # Schedule the generate_images_for_all_subcategories function to run every hour
    schedule(
        'sync.scripts.sync.run',
        schedule_type=Schedule.DAILY,
        repeats=-1,
        name='sync_process',
    )

    print("Schedules created successfully")

def run():
    create_schedules()

if __name__ == '__main__':
    run()
