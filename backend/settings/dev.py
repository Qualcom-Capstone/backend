# backend/settings/dev.py
from .base import *
from dotenv import load_dotenv

env_path = os.path.join(BASE_DIR, "backend.env")
if os.path.exists(env_path):
    load_dotenv(env_path)

DEBUG = True
ALLOWED_HOSTS = ["*"]

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

CORS_ORIGIN_ALLOW_ALL = True
