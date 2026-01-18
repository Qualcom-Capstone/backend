from rest_framework import serializers
from .models import Notification, NotificationLog


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id', 'detection', 'fcm_token', 'title', 'body',
            'sent_at', 'status', 'retry_count', 'error_message',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class NotificationListSerializer(serializers.ModelSerializer):
    detection_id = serializers.IntegerField(source='detection.id', read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'detection_id', 'title', 'status', 'sent_at', 'retry_count'
        ]


# 레거시 호환
class NotificationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationLog
        fields = '__all__'

