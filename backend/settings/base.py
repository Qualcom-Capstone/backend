# backend/settings/base.py
import os
from pathlib import Path
import pymysql

pymysql.install_as_MySQLdb()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "insecure-key")

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

# Celery 설정 추가
CELERY_BROKER_URL = 'amqp://guest:guest@rabbitmq:5672/'
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Seoul'

CELERY_TASK_TIME_LIMIT = 30 * 60

CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# Celery task를 종료 가능하게 해주는 세팅 (굉장히 중요)
CELERY_TASK_REVOKE = True

CELERYD_HIJACK_ROOT_LOGGER = False
CELERYD_REDIRECT_STDOUTS = False

CELERY_FLOWER_USER = 'root'  # Flower 웹 인터페이스 사용자 이름
CELERY_FLOWER_PASSWORD = 'root'  # Flower 웹 인터페이스 비밀번호

# CELERY_RESULT_BACKEND = 'rpc://'
CELERY_RESULT_BACKEND = "django-db"
