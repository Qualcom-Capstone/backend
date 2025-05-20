# backend/settings/prod.py
from .base import *

DEBUG = False
ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "backend",  # 내부 컨테이너 간 통신
    "api.autonotify.store",
    "www.autonotify.store",
    "autonotify.store"
]


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv("MYSQL_DATABASE"),
        'USER': os.getenv("MYSQL_USER"),
        'PASSWORD': os.getenv("MYSQL_PASSWORD"),
        'HOST': 'mysqldb',
        'PORT': int(os.getenv("DB_PORT", 3306)),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}

CORS_ORIGIN_ALLOW_ALL = False
