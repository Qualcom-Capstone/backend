from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DetectionViewSet

router = DefaultRouter()
router.register(r"detections", DetectionViewSet, basename="detection")

urlpatterns = [
    path("", include(router.urls)),
]
