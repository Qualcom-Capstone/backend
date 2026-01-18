"""
Unit Tests for DRF Serializers
"""
import pytest
from django.utils import timezone
from apps.vehicles.serializers import VehicleSerializer
from apps.detections.serializers import DetectionSerializer, DetectionListSerializer
from apps.notifications.serializers import NotificationSerializer, NotificationListSerializer


@pytest.mark.django_db
class TestVehicleSerializer:
    """Vehicle Serializer 테스트"""
    
    def test_serialize_vehicle(self, sample_vehicle):
        """Vehicle 직렬화 테스트"""
        serializer = VehicleSerializer(sample_vehicle)
        data = serializer.data
        
        assert data['plate_number'] == '12가3456'
        assert data['owner_name'] == '테스트 사용자'
        assert 'created_at' in data
    
    def test_deserialize_vehicle(self, db):
        """Vehicle 역직렬화 테스트"""
        data = {
            'plate_number': '56다7890',
            'owner_name': '새 사용자',
            'owner_phone': '010-1111-2222'
        }
        serializer = VehicleSerializer(data=data)
        
        assert serializer.is_valid()
        vehicle = serializer.save()
        assert vehicle.plate_number == '56다7890'
    
    def test_invalid_plate_number(self, db):
        """잘못된 차량 번호 테스트"""
        data = {
            'plate_number': '',  # 빈 문자열
            'owner_name': '테스트',
            'owner_phone': '010-1111-2222'
        }
        serializer = VehicleSerializer(data=data)
        
        assert not serializer.is_valid()
        assert 'plate_number' in serializer.errors


@pytest.mark.django_db
class TestDetectionSerializer:
    """Detection Serializer 테스트"""
    
    def test_serialize_detection(self, sample_detection):
        """Detection 직렬화 테스트"""
        serializer = DetectionSerializer(sample_detection)
        data = serializer.data
        
        assert data['camera_id'] == 'CAM-001'
        assert data['status'] == 'pending'
        assert data['detected_speed'] == 85.5
        assert data['speed_limit'] == 60.0
    
    def test_serialize_completed_detection(self, completed_detection):
        """완료된 Detection 직렬화 테스트"""
        serializer = DetectionSerializer(completed_detection)
        data = serializer.data
        
        assert data['status'] == 'completed'
        assert data['ocr_result'] == '12가3456'
        assert data['processed_at'] is not None
    
    def test_detection_with_vehicle_plate(self, sample_detection, sample_vehicle):
        """Vehicle이 연결된 Detection 직렬화 테스트 (ListSerializer)"""
        serializer = DetectionListSerializer(sample_detection)
        data = serializer.data
        
        assert data['vehicle_plate'] == '12가3456'


@pytest.mark.django_db
class TestNotificationSerializer:
    """Notification Serializer 테스트"""
    
    def test_serialize_notification(self, completed_detection, db):
        """Notification 직렬화 테스트"""
        from apps.notifications.models import Notification
        
        notification = Notification.objects.create(
            detection=completed_detection,
            fcm_token='test-token',
            title='테스트 알림',
            body='테스트 내용',
            status='sent',
            sent_at=timezone.now()
        )
        
        serializer = NotificationSerializer(notification)
        data = serializer.data
        
        assert data['title'] == '테스트 알림'
        assert data['status'] == 'sent'
        assert data['detection'] == completed_detection.id
    
    def test_serialize_notification_list(self, completed_detection, db):
        """Notification List 직렬화 테스트"""
        from apps.notifications.models import Notification
        
        notification = Notification.objects.create(
            detection=completed_detection,
            fcm_token='test-token',
            title='리스트 알림',
            body='테스트 내용',
            status='sent',
            sent_at=timezone.now()
        )
        
        serializer = NotificationListSerializer(notification)
        data = serializer.data
        
        assert data['detection_id'] == completed_detection.id

