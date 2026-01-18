# config/settings/dev.py
from .base import *
from dotenv import load_dotenv

# 환경변수 로드
env_path = os.path.join(BASE_DIR, "backend.env")
if os.path.exists(env_path):
    load_dotenv(env_path)

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME', 'speedcam'),
        'USER': os.getenv('DB_USER', 'sa'),
        'PASSWORD': os.getenv('DB_PASSWORD', '1234'),
        'HOST': os.getenv('DB_HOST', 'mysql'),
        'PORT': int(os.getenv('DB_PORT', 3306)),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}

# CORS
CORS_ORIGIN_ALLOW_ALL = True

# Celery (개발용 설정 오버라이드)
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'amqp://sa:1234@rabbitmq:5672//')

# 로깅 레벨
LOGGING['root']['level'] = 'DEBUG'
LOGGING['loggers']['django']['level'] = 'DEBUG'
