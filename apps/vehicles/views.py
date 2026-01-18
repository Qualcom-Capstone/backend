from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Vehicle, DeviceToken
from .serializers import (
    VehicleSerializer, 
    VehicleCreateSerializer,
    FCMTokenUpdateSerializer,
    DeviceTokenSerializer
)


class VehicleViewSet(viewsets.ModelViewSet):
    """차량 정보 관리 API"""
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer

    def get_serializer_class(self):
        if self.action == 'create':
            return VehicleCreateSerializer
        return VehicleSerializer

    @action(detail=True, methods=['patch'], url_path='fcm-token')
    def update_fcm_token(self, request, pk=None):
        """FCM 토큰 업데이트"""
        vehicle = self.get_object()
        serializer = FCMTokenUpdateSerializer(data=request.data)
        
        if serializer.is_valid():
            vehicle.fcm_token = serializer.validated_data['fcm_token']
            vehicle.save(update_fields=['fcm_token', 'updated_at'])
            return Response(VehicleSerializer(vehicle).data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='register-fcm')
    def register_fcm(self, request):
        """번호판 기반 FCM 토큰 등록"""
        plate_number = request.data.get('plate_number')
        fcm_token = request.data.get('fcm_token')
        
        if not plate_number or not fcm_token:
            return Response(
                {'error': 'plate_number and fcm_token are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        vehicle, created = Vehicle.objects.update_or_create(
            plate_number=plate_number,
            defaults={'fcm_token': fcm_token}
        )
        
        return Response(
            VehicleSerializer(vehicle).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class DeviceTokenViewSet(viewsets.ModelViewSet):
    """레거시 디바이스 토큰 API (호환용)"""
    queryset = DeviceToken.objects.all()
    serializer_class = DeviceTokenSerializer

