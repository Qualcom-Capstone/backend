from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
import logging


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings.prod')

app = Celery('backend', broker='amqp://guest:guest@rabbitmq:5672/')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()

app.log.setup_logging_subsystem()
logger = logging.getLogger('backend')
logger.setLevel(logging.DEBUG)