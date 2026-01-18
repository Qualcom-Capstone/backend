from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import VehicleViewSet, DeviceTokenViewSet

router = DefaultRouter()
router.register(r'vehicles', VehicleViewSet, basename='vehicle')
router.register(r'device-tokens', DeviceTokenViewSet, basename='device-token')

urlpatterns = [
    path('', include(router.urls)),
]

