from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from kombu import Exchange, Queue

import logging

app = Celery("backend")

app.conf.update(
    broker_url=os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672//"),
    result_backend="rpc://",
    task_acks_late=True,                # 작업 성공 시점에 ACK
    task_reject_on_worker_lost=True,    # 워커 죽으면 NACK
)

speeding_x        = Exchange("speeding_x",        type="direct")
speeding_dlx      = Exchange("speeding_dlx",      type="direct")   # DLQ 전용

app.conf.task_queues = (
    Queue(
        "speeding_alert",
        exchange=speeding_x,
        routing_key="speeding.alert",
        queue_arguments={
            "x-dead-letter-exchange": "speeding_dlx",
            "x-dead-letter-routing-key": "speeding.alert.dlq",
        },
    ),
    Queue(
        "speeding_alert_dlq",
        exchange=speeding_dlx,
        routing_key="speeding.alert.dlq",
        durable=True,
    ),
)

app.conf.task_routes = {
    "crud.tasks.send_speeding_alert":   {"queue": "speeding_alert"},
    "crud.tasks.handle_dlq_event":      {"queue": "speeding_alert_dlq"},
}

app.autodiscover_tasks()