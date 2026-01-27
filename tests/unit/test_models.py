"""
Unit Tests for Django Models
"""

import pytest
from django.db import IntegrityError

from apps.notifications.models import Notification
from apps.vehicles.models import Vehicle


@pytest.mark.django_db
class TestVehicleModel:
    """Vehicle 모델 테스트"""

    def test_create_vehicle(self, sample_vehicle):
        """Vehicle 생성 테스트"""
        assert sample_vehicle.pk is not None
        assert sample_vehicle.plate_number == "12가3456"
        assert sample_vehicle.owner_name == "테스트 사용자"

    def test_vehicle_str(self, sample_vehicle):
        """Vehicle __str__ 테스트"""
        assert str(sample_vehicle) == "12가3456"

    def test_vehicle_unique_plate(self, sample_vehicle, db):
        """차량 번호 중복 불가 테스트"""
        with pytest.raises(IntegrityError):
            Vehicle.objects.create(
                plate_number="12가3456",  # 중복
                owner_name="다른 사용자",
                owner_phone="010-0000-0000",
            )

    def test_vehicle_timestamps(self, sample_vehicle):
        """타임스탬프 자동 생성 테스트"""
        assert sample_vehicle.created_at is not None
        assert sample_vehicle.updated_at is not None


@pytest.mark.django_db
class TestDetectionModel:
    """Detection 모델 테스트"""

    def test_create_detection(self, sample_detection):
        """Detection 생성 테스트"""
        assert sample_detection.pk is not None
        assert sample_detection.camera_id == "CAM-001"
        assert sample_detection.status == "pending"

    def test_detection_str(self, sample_detection):
        """Detection __str__ 테스트"""
        # __str__ = f"{self.ocr_result or 'Unknown'} - {self.detected_speed}km/h"
        expected = f"Unknown - {sample_detection.detected_speed}km/h"
        assert str(sample_detection) == expected

    def test_detection_status_choices(self, pending_detection):
        """Detection status 변경 테스트"""
        assert pending_detection.status == "pending"

        pending_detection.status = "processing"
        pending_detection.save()
        pending_detection.refresh_from_db()
        assert pending_detection.status == "processing"

        pending_detection.status = "completed"
        pending_detection.save()
        pending_detection.refresh_from_db()
        assert pending_detection.status == "completed"

    def test_detection_vehicle_relation(self, sample_detection, sample_vehicle):
        """Detection-Vehicle 관계 테스트"""
        assert sample_detection.vehicle == sample_vehicle
        assert sample_detection in sample_vehicle.detections.all()

    def test_detection_speed_violation(self, sample_detection):
        """과속 여부 확인"""
        assert sample_detection.detected_speed > sample_detection.speed_limit

    def test_detection_nullable_fields(self, pending_detection):
        """Nullable 필드 테스트"""
        assert pending_detection.vehicle is None
        assert pending_detection.ocr_result is None
        assert pending_detection.processed_at is None


@pytest.mark.django_db
class TestNotificationModel:
    """Notification 모델 테스트"""

    def test_create_notification(self, completed_detection, db):
        """Notification 생성 테스트"""
        notification = Notification.objects.create(
            detection=completed_detection,
            fcm_token="test-token",
            title="테스트 알림",
            body="테스트 내용",
            status="pending",
        )
        assert notification.pk is not None
        assert notification.status == "pending"

    def test_notification_str(self, completed_detection, db):
        """Notification __str__ 테스트"""
        notification = Notification.objects.create(
            detection=completed_detection,
            fcm_token="test-token",
            title="테스트 알림",
            body="테스트 내용",
            status="sent",
        )
        # __str__ = f"Notification for Detection #{self.detection_id} - {self.status}"
        expected = f"Notification for Detection #{completed_detection.id} - sent"
        assert str(notification) == expected

    def test_notification_retry_count(self, completed_detection, db):
        """재시도 횟수 테스트"""
        notification = Notification.objects.create(
            detection=completed_detection,
            fcm_token="test-token",
            title="테스트 알림",
            body="테스트 내용",
            status="failed",
            retry_count=0,
        )

        # 재시도 횟수 증가
        notification.retry_count += 1
        notification.save()
        notification.refresh_from_db()
        assert notification.retry_count == 1

    def test_notification_detection_relation(self, completed_detection, db):
        """Notification-Detection 관계 테스트"""
        notification = Notification.objects.create(
            detection=completed_detection,
            fcm_token="test-token",
            title="테스트 알림",
            body="테스트 내용",
            status="sent",
        )
        assert notification.detection == completed_detection
        assert notification in completed_detection.notifications.all()
