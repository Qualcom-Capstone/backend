#!/bin/bash
set -e

echo "Starting Main Service (Django)..."

# Django 마이그레이션
echo "Running migrations..."
python manage.py migrate --noinput

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
gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers ${GUNICORN_WORKERS:-4} \
    --threads ${GUNICORN_THREADS:-2} \
    --access-logfile - \
    --error-logfile -
