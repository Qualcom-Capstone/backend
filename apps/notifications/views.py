from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets

from .models import Notification
from .serializers import NotificationListSerializer, NotificationSerializer


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """알림 이력 API (MSA: notifications_db 사용)"""

    queryset = Notification.objects.using("notifications_db").all()
    serializer_class = NotificationSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["status", "detection_id"]
    ordering_fields = ["sent_at", "created_at"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return NotificationListSerializer
        return NotificationSerializer
