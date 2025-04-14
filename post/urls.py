from backend.urls import path, include
from .views import SpeedViolationViewSet
#ViewSet을 사용하여 curd 엔드포인트 자동 생성
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'violations', SpeedViolationViewSet, basename='violation')
urlpatterns = [
    path("", include(router.urls)),
]