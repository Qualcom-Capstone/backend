from rest_framework import viewsets
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend

from .models import Notification, NotificationLog
from .serializers import (
    NotificationSerializer,
    NotificationListSerializer,
    NotificationLogSerializer
)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """알림 이력 API"""
    queryset = Notification.objects.select_related('detection').all()
    serializer_class = NotificationSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'detection']
    ordering_fields = ['sent_at', 'created_at']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return NotificationListSerializer
        return NotificationSerializer


class NotificationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """레거시 알림 로그 API (호환용)"""
    queryset = NotificationLog.objects.all()
    serializer_class = NotificationLogSerializer
    ordering = ['-created_at']

