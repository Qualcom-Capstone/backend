"""
URL configuration for speedcam project.
"""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path, re_path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework.permissions import AllowAny


def home(request):
    """API 홈 엔드포인트"""
    return JsonResponse(
        {
            "service": "SpeedCam API",
            "version": "v1",
            "status": "running",
            "endpoints": {
                "swagger": "/swagger/",
                "redoc": "/redoc/",
                "admin": "/admin/",
                "api_v1": "/api/v1/",
            },
        }
    )


def health(request):
    """헬스체크 엔드포인트 (외부 의존성 검증 포함)"""
    checks = {}

    # DB 연결 확인
    from django.db import connections

    for db_name in connections:
        try:
            connections[db_name].ensure_connection()
            checks[db_name] = "ok"
        except Exception as e:
            checks[db_name] = f"error: {e}"

    # RabbitMQ 연결 확인
    try:
        from config.celery import app as celery_app

        conn = celery_app.connection()
        conn.ensure_connection(max_retries=1, timeout=3)
        conn.close()
        checks["rabbitmq"] = "ok"
    except Exception as e:
        checks["rabbitmq"] = f"error: {e}"

    is_healthy = all(v == "ok" for v in checks.values())
    status_code = 200 if is_healthy else 503

    return JsonResponse(
        {"status": "healthy" if is_healthy else "unhealthy", "checks": checks},
        status=status_code,
    )


schema_view = get_schema_view(
    openapi.Info(
        title="SpeedCam API",
        default_version="v1",
        description="과속 차량 감지 및 알림 시스템 API",
        contact=openapi.Contact(email="admin@speedcam.local"),
    ),
    public=True,
    permission_classes=[AllowAny],
)

urlpatterns = [
    # 홈 & 헬스체크
    path("", home, name="home"),
    path("health/", health, name="health"),
    # Admin
    path("admin/", admin.site.urls),
    # API Documentation
    re_path(
        r"^swagger(?P<format>\.json|\.yaml)$",
        schema_view.without_ui(cache_timeout=0),
        name="schema-json",
    ),
    re_path(
        r"^swagger/$",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    re_path(
        r"^redoc/$", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"
    ),
    # API v1
    path("api/v1/", include("apps.vehicles.urls")),
    path("api/v1/", include("apps.detections.urls")),
    path("api/v1/", include("apps.notifications.urls")),
]
