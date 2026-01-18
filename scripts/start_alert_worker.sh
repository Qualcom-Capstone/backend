#!/bin/bash
set -e

echo "Starting Alert Worker (Celery)..."

# DataDog APM 활성화 (선택)
export DD_SERVICE="${DD_SERVICE:-speedcam-alert}"
export DD_ENV="${DD_ENV:-dev}"

# Celery Worker 시작 (gevent pool - I/O 집약적)
if [ -n "$DD_API_KEY" ]; then
    ddtrace-run celery -A config worker \
        --pool=gevent \
        --concurrency=${ALERT_CONCURRENCY:-100} \
        --queues=fcm_queue \
        --hostname=alert@%h \
        --loglevel=${LOG_LEVEL:-info}
else
    celery -A config worker \
        --pool=gevent \
        --concurrency=${ALERT_CONCURRENCY:-100} \
        --queues=fcm_queue \
        --hostname=alert@%h \
        --loglevel=${LOG_LEVEL:-info}
fi

