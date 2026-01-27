"""Celery Configuration"""

from __future__ import absolute_import, unicode_literals

import os

from celery import Celery
from kombu import Exchange, Queue

# Django settings 모듈 설정
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("speedcam")

# Exchange 정의
ocr_exchange = Exchange("ocr_exchange", type="direct", durable=True)
fcm_exchange = Exchange("fcm_exchange", type="direct", durable=True)
dlq_exchange = Exchange("dlq_exchange", type="fanout", durable=True)


# Celery 설정
app.conf.update(
    # 브로커 설정
    broker_url=os.getenv("CELERY_BROKER_URL", "amqp://sa:1234@rabbitmq:5672//"),
    result_backend="rpc://",
    # 직렬화
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # 시간대
    timezone="Asia/Seoul",
    enable_utc=True,
    # 안정성
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    # Timeout
    task_time_limit=300,
    task_soft_time_limit=240,
    # Prefetch
    worker_prefetch_multiplier=1,
)

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
}

# Task 자동 발견
app.autodiscover_tasks(["tasks"])
