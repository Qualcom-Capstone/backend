#!/bin/bash
set -e

echo "Starting Main Service (Django)..."

# ==================================================
# MSA Database Migration
# 각 서비스별 DB에 마이그레이션 실행
# ==================================================

echo "Running migrations for all databases..."

# 1. Default DB (Django 기본 - auth, admin, sessions)
echo "[1/4] Migrating default database..."
python manage.py migrate --database=default --noinput

# 2. Vehicles DB
echo "[2/4] Migrating vehicles database..."
python manage.py migrate --database=vehicles_db --noinput

# 3. Detections DB
echo "[3/4] Migrating detections database..."
python manage.py migrate --database=detections_db --noinput

# 4. Notifications DB
echo "[4/4] Migrating notifications database..."
python manage.py migrate --database=notifications_db --noinput

echo "All migrations completed!"

# Static 파일 수집 (프로덕션)
if [ "$DJANGO_SETTINGS_MODULE" = "config.settings.prod" ]; then
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
fi

# MQTT Subscriber 백그라운드 실행
echo "Starting MQTT Subscriber..."
python -c "
import django
django.setup()
from core.mqtt.subscriber import start_mqtt_subscriber
start_mqtt_subscriber()
" &

# Gunicorn 시작
echo "Starting Gunicorn..."
opentelemetry-instrument \
    --service_name speedcam-api \
    gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers ${GUNICORN_WORKERS:-4} \
    --threads ${GUNICORN_THREADS:-2} \
    --access-logfile - \
    --error-logfile -
