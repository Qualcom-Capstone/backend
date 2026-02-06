import logging
import os

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Vehicle
from .serializers import (
    FCMTokenUpdateSerializer,
    VehicleCreateSerializer,
    VehicleSerializer,
)

logger = logging.getLogger(__name__)


class VehicleViewSet(viewsets.ModelViewSet):
    """차량 정보 관리 API (MSA: vehicles_db 사용)"""

    queryset = Vehicle.objects.using("vehicles_db").all()
    serializer_class = VehicleSerializer

    def get_serializer_class(self):
        if self.action == "create":
            return VehicleCreateSerializer
        return VehicleSerializer

    def perform_create(self, serializer):
        """생성 시 vehicles_db에 저장 (Router가 자동 라우팅)"""
        serializer.save()

    def perform_update(self, serializer):
        """업데이트 시 vehicles_db 사용 (Router가 자동 라우팅)"""
        serializer.save()

    @action(detail=True, methods=["patch"], url_path="fcm-token")
    def update_fcm_token(self, request, pk=None):
        """FCM 토큰 업데이트"""
        vehicle = self.get_object()
        serializer = FCMTokenUpdateSerializer(data=request.data)

        if serializer.is_valid():
            vehicle.fcm_token = serializer.validated_data["fcm_token"]
            vehicle.save(using="vehicles_db", update_fields=["fcm_token", "updated_at"])
            return Response(VehicleSerializer(vehicle).data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path="register-fcm")
    def register_fcm(self, request):
        """번호판 기반 FCM 토큰 등록"""
        plate_number = request.data.get("plate_number")
        fcm_token = request.data.get("fcm_token")

        if not plate_number or not fcm_token:
            return Response(
                {"error": "plate_number and fcm_token are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vehicle, created = Vehicle.objects.using("vehicles_db").update_or_create(
            plate_number=plate_number, defaults={"fcm_token": fcm_token}
        )

        # Dashboard 토큰은 FCM 토픽에 구독
        if plate_number == "DASHBOARD":
            try:
                FCM_MOCK = os.getenv("FCM_MOCK", "false").lower() == "true"
                if FCM_MOCK:
                    logger.info("[MOCK] Would subscribe token to dashboard_alerts topic")
                else:
                    from core.firebase.fcm import get_fcm_client

                    fcm_client = get_fcm_client()
                    fcm_client.subscribe_to_topic([fcm_token], "dashboard_alerts")
                    logger.info("Dashboard token subscribed to dashboard_alerts topic")
            except Exception as e:
                logger.warning(f"Failed to subscribe dashboard token to topic: {e}")

        return Response(
            VehicleSerializer(vehicle).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
