#!/bin/bash
set -e

echo "Starting OCR Worker (Celery)..."

# Celery Worker 시작 (prefork pool - CPU 집약적)
celery -A config worker \
    --pool=prefork \
    --concurrency=${OCR_CONCURRENCY:-4} \
    --queues=ocr_queue \
    --hostname=ocr@%h \
    --loglevel=${LOG_LEVEL:-info}
