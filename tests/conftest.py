"""
Pytest Configuration and Fixtures
"""
import os
import pytest
from unittest.mock import MagicMock, patch

# Django 설정
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

import django
django.setup()

from django.utils import timezone
from apps.vehicles.models import Vehicle
from apps.detections.models import Detection
from apps.notifications.models import Notification


@pytest.fixture
def sample_vehicle(db):
    """테스트용 Vehicle 생성"""
    return Vehicle.objects.create(
        plate_number='12가3456',
        owner_name='테스트 사용자',
        owner_phone='010-1234-5678',
        fcm_token='test-fcm-token-12345'
    )


@pytest.fixture
def sample_vehicle_no_fcm(db):
    """FCM 토큰 없는 Vehicle 생성"""
    return Vehicle.objects.create(
        plate_number='34나5678',
        owner_name='테스트 사용자2',
        owner_phone='010-9876-5432'
    )


@pytest.fixture
def sample_detection(db, sample_vehicle):
    """테스트용 Detection 생성"""
    return Detection.objects.create(
        vehicle=sample_vehicle,
        camera_id='CAM-001',
        location='테스트 위치',
        detected_speed=85.5,
        speed_limit=60.0,
        detected_at=timezone.now(),
        image_gcs_uri='gs://test-bucket/test-image.jpg',
        status='pending'
    )


@pytest.fixture
def pending_detection(db):
    """Pending 상태의 Detection"""
    return Detection.objects.create(
        camera_id='CAM-TEST-001',
        location='테스트 위치',
        detected_speed=95.0,
        speed_limit=60.0,
        detected_at=timezone.now(),
        image_gcs_uri='gs://test-bucket/pending-test.jpg',
        status='pending'
    )


@pytest.fixture
def completed_detection(db, sample_vehicle):
    """Completed 상태의 Detection"""
    return Detection.objects.create(
        vehicle=sample_vehicle,
        camera_id='CAM-TEST-002',
        location='완료 테스트 위치',
        detected_speed=100.0,
        speed_limit=60.0,
        detected_at=timezone.now(),
        processed_at=timezone.now(),
        image_gcs_uri='gs://test-bucket/completed-test.jpg',
        ocr_result='12가3456',
        ocr_confidence=0.95,
        status='completed'
    )


@pytest.fixture
def mock_celery_task():
    """Celery Task Mock"""
    with patch('celery.app.task.Task.apply_async') as mock:
        mock.return_value = MagicMock(id='mock-task-id')
        yield mock


@pytest.fixture
def mock_fcm():
    """Firebase FCM Mock"""
    with patch('firebase_admin.messaging.send') as mock:
        mock.return_value = 'mock-message-id'
        yield mock


@pytest.fixture
def mock_gcs():
    """Google Cloud Storage Mock"""
    with patch('google.cloud.storage.Client') as mock:
        mock_blob = MagicMock()
        mock_blob.download_as_bytes.return_value = b'fake-image-data'
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock.return_value.bucket.return_value = mock_bucket
        yield mock

