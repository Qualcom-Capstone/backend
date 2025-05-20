# backend/settings/base.py
import os
from pathlib import Path
import pymysql
from kombu import Queue

pymysql.install_as_MySQLdb()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "insecure-key")

# S3 설정
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_KEY')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_S3_BUCKET_NAME')
AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION')


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "post",
    "rest_framework",
    "drf_yasg",
    "crud",
    'django_celery_beat',
    'django_celery_results',
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "backend.wsgi.application"

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "static")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SWAGGER_SETTINGS = {
    "SECURITY_DEFINITIONS": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
        }
    },
    "USE_SESSION_AUTH": False,
}

# 기본 브로커 및 직렬화 설정은 유지
CELERY_BROKER_URL = 'amqp://guest:guest@rabbitmq:5672/'
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Seoul'
CELERY_RESULT_BACKEND = 'rpc://'

# Task 재시도, DLQ 등을 위한 안정성 관련 설정
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_REVOKE = True

# 로그 설정
CELERYD_HIJACK_ROOT_LOGGER = False
CELERYD_REDIRECT_STDOUTS = False

# Flower 관리자 계정
CELERY_FLOWER_USER = 'root'
CELERY_FLOWER_PASSWORD = 'root'

# ✅ [추가] Task 라우팅 큐 설정
CELERY_TASK_QUEUES = (
    Queue('fcm_notify_queue', routing_key='fcm_notify'),
    Queue('dlq_notify_queue', routing_key='dlq_notify'),
)

CELERY_TASK_ROUTES = {
    'crud.tasks.send_speeding_alert': {
        'queue': 'fcm_notify_queue',
        'routing_key': 'fcm_notify'
    },
    'crud.tasks.handle_dlq_event': {
        'queue': 'dlq_notify_queue',
        'routing_key': 'dlq_notify'
    },
}

# DLQ 설정
CELERY_TASK_QUEUE_MAX_PRIORITY = 10
CELERY_TASK_DEFAULT_PRIORITY = 5
CELERY_TASK_QUEUE_DEFAULT_PRIORITY = 5

# DLQ 관련 설정
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30분
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25분
