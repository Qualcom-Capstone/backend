"""Celery Configuration"""

import os

from celery import Celery
from kombu import Exchange, Queue

# Django settings 모듈 설정
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("speedcam")

# Django settings에서 CELERY_ prefix 설정을 자동으로 읽어옴
app.config_from_object("django.conf:settings", namespace="CELERY")

# Exchange 정의
ocr_exchange = Exchange("ocr_exchange", type="direct", durable=True)
fcm_exchange = Exchange("fcm_exchange", type="direct", durable=True)
dlq_exchange = Exchange("dlq_exchange", type="fanout", durable=True)

# Queue 정의
app.conf.task_queues = (
    # 새로운 Queue (PRD 구조)
    Queue(
        "ocr_queue",
        exchange=ocr_exchange,
        routing_key="ocr",
        queue_arguments={
            "x-dead-letter-exchange": "dlq_exchange",
            "x-message-ttl": 3600000,
            "x-max-priority": 10,
        },
    ),
    Queue(
        "fcm_queue",
        exchange=fcm_exchange,
        routing_key="fcm",
        queue_arguments={
            "x-dead-letter-exchange": "dlq_exchange",
            "x-message-ttl": 3600000,
        },
    ),
    Queue(
        "dlq_queue",
        exchange=dlq_exchange,
        routing_key="",
    ),
)

# Task 라우팅
app.conf.task_routes = {
    # 새로운 Tasks (PRD 구조)
    "tasks.ocr_tasks.process_ocr": {
        "queue": "ocr_queue",
        "exchange": "ocr_exchange",
        "routing_key": "ocr",
    },
    "tasks.notification_tasks.send_notification": {
        "queue": "fcm_queue",
        "exchange": "fcm_exchange",
        "routing_key": "fcm",
    },
    "tasks.dlq_tasks.process_dlq_message": {
        "queue": "dlq_queue",
        "exchange": "dlq_exchange",
        "routing_key": "",
    },
}

# Task 자동 발견
app.autodiscover_tasks(["tasks"])
