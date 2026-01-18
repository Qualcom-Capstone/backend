#!/bin/bash
set -e

echo "Starting OCR Worker (Celery)..."

# DataDog APM 활성화 (선택)
export DD_SERVICE="${DD_SERVICE:-speedcam-ocr}"
export DD_ENV="${DD_ENV:-dev}"

# Celery Worker 시작 (prefork pool - CPU 집약적)
if [ -n "$DD_API_KEY" ]; then
    ddtrace-run celery -A config worker \
        --pool=prefork \
        --concurrency=${OCR_CONCURRENCY:-4} \
        --queues=ocr_queue \
        --hostname=ocr@%h \
        --loglevel=${LOG_LEVEL:-info}
else
    celery -A config worker \
        --pool=prefork \
        --concurrency=${OCR_CONCURRENCY:-4} \
        --queues=ocr_queue \
        --hostname=ocr@%h \
        --loglevel=${LOG_LEVEL:-info}
fi

