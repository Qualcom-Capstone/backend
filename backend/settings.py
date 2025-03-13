import os
from dotenv import load_dotenv
from pathlib import Path
import pymysql

# PyMySQL을 MySQLdb로 인식하게 설정 (mysqlclient 없이 사용 가능)
pymysql.install_as_MySQLdb()

# BASE_DIR 설정
BASE_DIR = Path(__file__).resolve().parent.parent

# .env 파일 로드 (backend.env만 사용)
env_path = os.path.join(BASE_DIR, "backend.env")
if os.path.exists(env_path):
    load_dotenv(env_path)

# SECRET_KEY 로드
SECRET_KEY = os.getenv("SECRET_KEY")

# DEBUG 설정
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

# ALLOWED_HOSTS 설정
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# Application definition
INSTALLED_APPS = [
    # "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    # "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "post",
    "rest_framework",
    "drf_yasg",  # Swagger 추가
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # "django.contrib.sessions.middleware.SessionMiddleware",
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

# ✅ Database 설정 (환경 변수 기반)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'capstone',  # docker-compose에서 설정한 MYSQL_DATABASE 값
        'USER': 'sa',  # docker-compose에서 설정한 MYSQL_USER 값
        'PASSWORD': '1234',  # docker-compose에서 설정한 MYSQL_PASSWORD 값
        'HOST': 'mysqldb',  # docker-compose의 서비스 이름 (컨테이너 내부에서 접속할 때 사용)
        'PORT': 3306,  # 기본 MySQL 포트
        'OPTIONS': {
            'charset': 'utf8mb4',  # UTF-8 문자 인코딩 설정 (이모지 지원 포함)
        },
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "static")

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Swagger 설정
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
