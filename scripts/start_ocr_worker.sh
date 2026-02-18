#!/bin/bash
set -e

echo "Starting OCR Worker (Celery)..."

# GCP metadata 내부 요청을 트레이싱에서 제외 (404 ERROR span 방지)
export OTEL_PYTHON_REQUESTS_EXCLUDED_URLS="${OTEL_PYTHON_REQUESTS_EXCLUDED_URLS:-metadata.google.internal}"

# Celery Worker 시작 (prefork pool - CPU 집약적)
opentelemetry-instrument \
    --service_name speedcam-ocr \
    celery -A config worker \
    --pool=prefork \
    --concurrency=${OCR_CONCURRENCY:-4} \
    --queues=ocr_queue \
    --hostname=ocr@%h \
    --loglevel=${LOG_LEVEL:-info}
