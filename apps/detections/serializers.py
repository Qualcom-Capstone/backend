from rest_framework import serializers
from .models import Detection, CarData
from apps.vehicles.serializers import VehicleSerializer


class DetectionSerializer(serializers.ModelSerializer):
    vehicle = VehicleSerializer(read_only=True)

    class Meta:
        model = Detection
        fields = [
            'id', 'vehicle', 'detected_speed', 'speed_limit',
            'location', 'camera_id', 'image_gcs_uri',
            'ocr_result', 'ocr_confidence',
            'detected_at', 'processed_at', 'status', 'error_message',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class DetectionListSerializer(serializers.ModelSerializer):
    """목록 조회용 간략 Serializer"""
    vehicle_plate = serializers.CharField(
        source='vehicle.plate_number', 
        read_only=True,
        default=None
    )

    class Meta:
        model = Detection
        fields = [
            'id', 'vehicle_plate', 'detected_speed', 'speed_limit',
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
    total_detections = serializers.IntegerField()
    completed_count = serializers.IntegerField()
    failed_count = serializers.IntegerField()
    pending_count = serializers.IntegerField()
    avg_speed = serializers.FloatField()
    max_speed = serializers.FloatField()


# 레거시 호환
class CarDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarData
        fields = '__all__'

