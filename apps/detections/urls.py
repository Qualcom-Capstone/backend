from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DetectionViewSet, CarDataViewSet

router = DefaultRouter()
router.register(r'detections', DetectionViewSet, basename='detection')
router.register(r'car-data', CarDataViewSet, basename='car-data')

urlpatterns = [
    path('', include(router.urls)),
]

