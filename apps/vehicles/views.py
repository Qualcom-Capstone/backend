from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Vehicle
from .serializers import (
    VehicleSerializer, 
    VehicleCreateSerializer,
    FCMTokenUpdateSerializer,
)


class VehicleViewSet(viewsets.ModelViewSet):
    """차량 정보 관리 API (MSA: vehicles_db 사용)"""
    queryset = Vehicle.objects.using('vehicles_db').all()
    serializer_class = VehicleSerializer

    def get_serializer_class(self):
        if self.action == 'create':
            return VehicleCreateSerializer
        return VehicleSerializer

    def perform_create(self, serializer):
        """생성 시 vehicles_db에 저장"""
        instance = Vehicle.objects.using('vehicles_db').create(
            **serializer.validated_data
        )
        serializer.instance = instance

    def perform_update(self, serializer):
        """업데이트 시 vehicles_db 사용"""
        instance = serializer.instance
        for attr, value in serializer.validated_data.items():
            setattr(instance, attr, value)
        instance.save(using='vehicles_db')

    @action(detail=True, methods=['patch'], url_path='fcm-token')
    def update_fcm_token(self, request, pk=None):
        """FCM 토큰 업데이트"""
        vehicle = self.get_object()
        serializer = FCMTokenUpdateSerializer(data=request.data)
        
        if serializer.is_valid():
            vehicle.fcm_token = serializer.validated_data['fcm_token']
            vehicle.save(using='vehicles_db', update_fields=['fcm_token', 'updated_at'])
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
        
        vehicle, created = Vehicle.objects.using('vehicles_db').update_or_create(
            plate_number=plate_number,
            defaults={'fcm_token': fcm_token}
        )
        
        return Response(
            VehicleSerializer(vehicle).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
