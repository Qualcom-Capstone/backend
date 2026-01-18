"""
URL configuration for speedcam project.
"""
from django.contrib import admin
from django.urls import path, include, re_path
from rest_framework.permissions import AllowAny
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.http import JsonResponse


def home(request):
    """API 홈 엔드포인트"""
    return JsonResponse({
        "service": "SpeedCam API",
        "version": "v1",
        "status": "running",
        "endpoints": {
            "swagger": "/swagger/",
            "redoc": "/redoc/",
            "admin": "/admin/",
            "api_v1": "/api/v1/",
        }
    })


def health(request):
    """헬스체크 엔드포인트"""
    return JsonResponse({"status": "healthy"})


schema_view = get_schema_view(
    openapi.Info(
        title="SpeedCam API",
        default_version='v1',
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
    path('admin/', admin.site.urls),
    
    # API Documentation
    re_path(
        r'^swagger(?P<format>\.json|\.yaml)$',
        schema_view.without_ui(cache_timeout=0),
        name='schema-json'
    ),
    re_path(
        r'^swagger/$',
        schema_view.with_ui('swagger', cache_timeout=0),
        name='schema-swagger-ui'
    ),
    re_path(
        r'^redoc/$',
        schema_view.with_ui('redoc', cache_timeout=0),
        name='schema-redoc'
    ),

    # API v1
    path('api/v1/', include('apps.vehicles.urls')),
    path('api/v1/', include('apps.detections.urls')),
    path('api/v1/', include('apps.notifications.urls')),
]
