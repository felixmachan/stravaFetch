import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pacepilot.settings')
app = Celery('pacepilot')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
