#!/bin/sh
set -e

echo "Starting Alert Worker (Kombu Consumer + Celery FCM Worker)..."

# Django 설정 모듈 기본값
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.dev}"

# GCP metadata 내부 요청을 트레이싱에서 제외 (404 ERROR span 방지)
export OTEL_PYTHON_REQUESTS_EXCLUDED_URLS="${OTEL_PYTHON_REQUESTS_EXCLUDED_URLS:-metadata.google.internal}"

# gevent monkey-patching을 OTel 초기화 전에 수행하도록 설정
# Celery gevent pool + OTel 조합에서 late patching으로 인한
# Django DB thread-safety 이슈 방지 (docs/GEVENT_DB_THREAD_SAFETY.md 참조)
export OTEL_PYTHON_AUTO_INSTRUMENTATION_EXPERIMENTAL_GEVENT_PATCH=patch_all

# ============================================================
# 프로세스 1: Kombu 이벤트 소비자 (백그라운드)
# - 단일 스레드, detections.completed 이벤트 수신
# - send_notification.delay()로 Celery에 위임
# ============================================================
opentelemetry-instrument \
    --service_name speedcam-alert-consumer \
    python -c "
import django
django.setup()
from core.events.consumer import start_event_consumer
start_event_consumer()
" &

CONSUMER_PID=$!
echo "Kombu consumer started (PID: $CONSUMER_PID)"

# ============================================================
# 프로세스 2: Celery gevent worker (포그라운드)
# - gevent pool, FCM 전송 병렬 처리
# - fcm_queue에서 send_notification 태스크 소비
# ============================================================
opentelemetry-instrument \
    --service_name speedcam-alert \
    celery -A config worker \
    --pool=gevent \
    --concurrency="${ALERT_CONCURRENCY:-100}" \
    --queues=fcm_queue \
    --hostname=alert@%h \
    --loglevel="${LOG_LEVEL:-info}" &

CELERY_PID=$!
echo "Celery FCM worker started (PID: $CELERY_PID)"

# 어느 하나라도 종료되면 나머지도 종료 (POSIX sh 호환)
trap "kill $CONSUMER_PID $CELERY_PID 2>/dev/null; exit" TERM INT

# wait -n은 bash 전용이므로 POSIX 호환 방식으로 대체
# 두 프로세스 중 하나라도 종료되면 감지
while kill -0 $CONSUMER_PID 2>/dev/null && kill -0 $CELERY_PID 2>/dev/null; do
    sleep 1
done

echo "A process exited, shutting down..."
kill $CONSUMER_PID $CELERY_PID 2>/dev/null || true
wait
