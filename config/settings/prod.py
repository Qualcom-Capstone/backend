# config/settings/prod.py
from .base import *

DEBUG = False
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")

# ==================================================
# MSA Database 설정
# ==================================================
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("DB_NAME", "speedcam"),
        "USER": DB_USER,
        "PASSWORD": DB_PASSWORD,
        "HOST": DB_HOST,
        "PORT": DB_PORT,
        "OPTIONS": {
            "charset": "utf8mb4",
        },
    },
    "vehicles_db": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("DB_NAME_VEHICLES", "speedcam_vehicles"),
        "USER": DB_USER,
        "PASSWORD": DB_PASSWORD,
        "HOST": DB_HOST,
        "PORT": DB_PORT,
        "OPTIONS": {
            "charset": "utf8mb4",
        },
    },
    "detections_db": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("DB_NAME_DETECTIONS", "speedcam_detections"),
        "USER": DB_USER,
        "PASSWORD": DB_PASSWORD,
        "HOST": DB_HOST,
        "PORT": DB_PORT,
        "OPTIONS": {
            "charset": "utf8mb4",
        },
    },
    "notifications_db": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("DB_NAME_NOTIFICATIONS", "speedcam_notifications"),
        "USER": DB_USER,
        "PASSWORD": DB_PASSWORD,
        "HOST": DB_HOST,
        "PORT": DB_PORT,
        "OPTIONS": {
            "charset": "utf8mb4",
        },
    },
}

# ==================================================
# Database Router 설정
# ==================================================
DATABASE_ROUTERS = ["config.db_router.MSADatabaseRouter"]

# ==================================================
# CORS 설정
# ==================================================
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
CORS_ALLOW_CREDENTIALS = True
