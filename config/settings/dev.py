# config/settings/dev.py
from .base import *
from dotenv import load_dotenv

# 환경변수 로드
env_path = os.path.join(BASE_DIR, "backend.env")
if os.path.exists(env_path):
    load_dotenv(env_path)

DEBUG = True
ALLOWED_HOSTS = ["*"]

# ==================================================
# MSA Database 설정
# ==================================================
# 각 서비스별 독립 DB 사용
# - default: Django 기본 테이블 (auth, admin, sessions 등)
# - vehicles_db: 차량 서비스
# - detections_db: 감지 서비스
# - notifications_db: 알림 서비스
# ==================================================

DB_HOST = os.getenv('DB_HOST', 'mysql')
DB_PORT = int(os.getenv('DB_PORT', 3306))
DB_USER = os.getenv('DB_USER', 'sa')
DB_PASSWORD = os.getenv('DB_PASSWORD', '1234')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME', 'speedcam'),
        'USER': DB_USER,
        'PASSWORD': DB_PASSWORD,
        'HOST': DB_HOST,
        'PORT': DB_PORT,
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    },
    'vehicles_db': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME_VEHICLES', 'speedcam_vehicles'),
        'USER': DB_USER,
        'PASSWORD': DB_PASSWORD,
        'HOST': DB_HOST,
        'PORT': DB_PORT,
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    },
    'detections_db': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME_DETECTIONS', 'speedcam_detections'),
        'USER': DB_USER,
        'PASSWORD': DB_PASSWORD,
        'HOST': DB_HOST,
        'PORT': DB_PORT,
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    },
    'notifications_db': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME_NOTIFICATIONS', 'speedcam_notifications'),
        'USER': DB_USER,
        'PASSWORD': DB_PASSWORD,
        'HOST': DB_HOST,
        'PORT': DB_PORT,
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    },
}

# ==================================================
# Database Router 설정
# ==================================================
DATABASE_ROUTERS = ['config.db_router.MSADatabaseRouter']

# CORS
CORS_ORIGIN_ALLOW_ALL = True

# Celery (개발용 설정 오버라이드)
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'amqp://sa:1234@rabbitmq:5672//')

# 로깅 레벨
LOGGING['root']['level'] = 'DEBUG'
LOGGING['loggers']['django']['level'] = 'DEBUG'
