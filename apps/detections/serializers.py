from rest_framework import serializers
from .models import Detection


class DetectionSerializer(serializers.ModelSerializer):
    """Detection 상세 Serializer"""
    
    class Meta:
        model = Detection
        fields = [
            'id', 'vehicle_id', 'detected_speed', 'speed_limit',
            'location', 'camera_id', 'image_gcs_uri',
            'ocr_result', 'ocr_confidence',
            'detected_at', 'processed_at', 'status', 'error_message',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class DetectionListSerializer(serializers.ModelSerializer):
    """목록 조회용 간략 Serializer"""
    
    class Meta:
        model = Detection
        fields = [
            'id', 'vehicle_id', 'detected_speed', 'speed_limit',
            'location', 'camera_id', 'ocr_result', 'status',
            'detected_at', 'processed_at'
        ]


class DetectionCreateSerializer(serializers.ModelSerializer):
    """MQTT 메시지로부터 생성용"""
    
    class Meta:
        model = Detection
        fields = [
            'detected_speed', 'speed_limit', 'location',
            'camera_id', 'image_gcs_uri', 'detected_at'
        ]


class DetectionStatisticsSerializer(serializers.Serializer):
    """통계 데이터 Serializer"""
    total_detections = serializers.IntegerField()
    completed_count = serializers.IntegerField()
    failed_count = serializers.IntegerField()
    pending_count = serializers.IntegerField()
    avg_speed = serializers.FloatField()
    max_speed = serializers.FloatField()
