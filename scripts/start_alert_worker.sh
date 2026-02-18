#!/bin/bash
set -e

echo "Starting Alert Worker (Domain Event Consumer)..."

# Django 설정 모듈 기본값
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.dev}"

# GCP metadata 내부 요청을 트레이싱에서 제외 (404 ERROR span 방지)
export OTEL_PYTHON_REQUESTS_EXCLUDED_URLS="${OTEL_PYTHON_REQUESTS_EXCLUDED_URLS:-metadata.google.internal}"

# gevent monkey-patching을 OTel 초기화 전에 수행하도록 설정
# 이 설정이 없으면 OTel이 ssl/urllib3를 먼저 import하여
# threading.local()이 greenlet-local로 패치되지 않아
# Django DB 커넥션이 greenlet 간 공유되는 thread-safety 문제 발생
# See: docs/GEVENT_DB_THREAD_SAFETY.md
export OTEL_PYTHON_AUTO_INSTRUMENTATION_EXPERIMENTAL_GEVENT_PATCH=patch_all

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
