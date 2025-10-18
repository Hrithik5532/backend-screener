
#ScreeneApp/celery.py
from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ScreeneApp.settings')

app = Celery('ScreeneApp')  # Use your actual project name

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')

# Celery settings for better async handling
from celery import signals

@signals.worker_process_init.connect
def init_worker(**kwargs):
    """Reset database connections after worker fork"""
    import asyncio
    # Create new event loop for this worker
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)