#!/bin/bash
set -e

echo "Starting Alert Worker (Domain Event Consumer)..."

# Django 설정 모듈 기본값
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.dev}"

# GCP metadata 내부 요청을 트레이싱에서 제외 (404 ERROR span 방지)
export OTEL_PYTHON_REQUESTS_EXCLUDED_URLS="${OTEL_PYTHON_REQUESTS_EXCLUDED_URLS:-metadata.google.internal}"

# Alert Event Consumer 시작
# Choreography: detections.completed 이벤트를 직접 구독하여
# Alert Service가 자율적으로 알림 발송 여부를 결정한다.
opentelemetry-instrument \
    --service_name speedcam-alert \
    python -c "
import django
django.setup()
from core.events.consumer import start_event_consumer
start_event_consumer()
"
