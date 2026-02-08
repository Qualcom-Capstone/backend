from django.db.models import Avg, Count, Max
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Detection
from .serializers import (
    DetectionListSerializer,
    DetectionSerializer,
    DetectionStatisticsSerializer,
)


class DetectionViewSet(viewsets.ReadOnlyModelViewSet):
    """과속 감지 내역 API (MSA: detections_db 사용)"""

    queryset = Detection.objects.using("detections_db").all()
    serializer_class = DetectionSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["status", "camera_id", "location"]
    ordering_fields = ["detected_at", "created_at", "detected_speed"]
    ordering = ["-detected_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return DetectionListSerializer
        return DetectionSerializer

    @action(detail=False, methods=["get"])
    def pending(self, request):
        """판독 중인 차량 목록"""
        pending_detections = self.queryset.filter(status__in=["pending", "processing"])
        serializer = DetectionListSerializer(pending_detections, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def statistics(self, request):
        """위반 통계"""
        from datetime import timedelta

        from django.utils import timezone

        queryset = Detection.objects.using("detections_db").all()

        # 기간 필터 (선택)
        period = request.query_params.get("period")
        period_map = {
            "today": timedelta(days=1),
            "week": timedelta(weeks=1),
            "month": timedelta(days=30),
        }
        if period in period_map:
            queryset = queryset.filter(
                detected_at__gte=timezone.now() - period_map[period]
            )

        # 카메라 필터 (선택)
        camera_id = request.query_params.get("camera_id")
        if camera_id:
            queryset = queryset.filter(camera_id=camera_id)

        stats = queryset.aggregate(
            total_detections=Count("id"),
            avg_speed=Avg("detected_speed"),
            max_speed=Max("detected_speed"),
        )

        stats["completed_count"] = queryset.filter(status="completed").count()
        stats["failed_count"] = queryset.filter(status="failed").count()
        stats["pending_count"] = queryset.filter(
            status__in=["pending", "processing"]
        ).count()

        # None 값 처리
        stats["avg_speed"] = stats["avg_speed"] or 0
        stats["max_speed"] = stats["max_speed"] or 0

        serializer = DetectionStatisticsSerializer(stats)
        return Response(serializer.data)
