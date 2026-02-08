#!/bin/bash
set -e

echo "Starting Alert Worker (Celery)..."

# Celery Worker 시작 (gevent pool - I/O 집약적)
opentelemetry-instrument \
    --service_name speedcam-alert \
    celery -A config worker \
    --pool=gevent \
    --concurrency=${ALERT_CONCURRENCY:-100} \
    --queues=fcm_queue \
    --hostname=alert@%h \
    --loglevel=${LOG_LEVEL:-info}
