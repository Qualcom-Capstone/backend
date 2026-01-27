from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Notification 상세 Serializer"""

    class Meta:
        model = Notification
        fields = [
            "id",
            "detection_id",
            "fcm_token",
            "title",
            "body",
            "sent_at",
            "status",
            "retry_count",
            "error_message",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class NotificationListSerializer(serializers.ModelSerializer):
    """목록 조회용 간략 Serializer"""

    class Meta:
        model = Notification
        fields = ["id", "detection_id", "title", "status", "sent_at", "retry_count"]


class NotificationCreateSerializer(serializers.ModelSerializer):
    """알림 생성용 Serializer"""

    class Meta:
        model = Notification
        fields = ["detection_id", "fcm_token", "title", "body"]
