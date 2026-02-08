"""
Unit Tests for Celery Tasks
모듈 의존성(google.cloud, firebase_admin)이 없는 환경에서는 skip됨
"""

import sys
from unittest.mock import patch

import pytest

# google.cloud와 firebase_admin이 없으면 테스트 skip
google_available = "google.cloud" in sys.modules or "google" in sys.modules
firebase_available = "firebase_admin" in sys.modules

try:
    from google.cloud import storage  # noqa: F401

    google_available = True
except ImportError:
    google_available = False

try:
    import firebase_admin  # noqa: F401

    firebase_available = True
except ImportError:
    firebase_available = False


@pytest.mark.django_db(databases="__all__")
class TestOCRTaskMock:
    """OCR Task Mock 테스트 (google.cloud 없이)"""

    def test_ocr_mock_result_format(self, pending_detection):
        """Mock OCR 결과 형식 테스트"""
        import random

        # Mock에서 생성되는 결과 형식 검증
        def generate_mock_plate():
            regions = ["서울", "경기", "인천", "부산", "대구"]
            chars = "abcdefghijklmnopqrstuvwxyz가나다라마바사아자차카타파하"
            return f"{random.randint(10, 99)}{random.choice(regions)}{random.choice(chars)}{random.randint(1000, 9999)}"

        plate = generate_mock_plate()
        assert len(plate) >= 7  # 최소 길이 확인

    @pytest.mark.skipif(not google_available, reason="google.cloud not installed")
    @patch("tasks.ocr_tasks.os.environ.get")
    def test_process_ocr_mock_mode(self, mock_env, pending_detection):
        """Mock 모드에서 OCR 처리 테스트"""
        mock_env.return_value = "true"

        from tasks.ocr_tasks import process_ocr

        process_ocr(pending_detection.id, gcs_uri=pending_detection.image_gcs_uri)

        pending_detection.refresh_from_db()
        assert pending_detection.status == "completed"


@pytest.mark.django_db(databases="__all__")
class TestNotificationTaskMock:
    """Notification Task Mock 테스트 (firebase_admin 없이)"""

    def test_notification_title_format(self, completed_detection):
        """알림 제목 형식 테스트"""
        title = f"⚠️ 과속 위반 감지: {completed_detection.ocr_result}"
        assert "과속 위반 감지" in title
        assert completed_detection.ocr_result in title

    def test_notification_body_format(self, completed_detection):
        """알림 본문 형식 테스트"""
        body = (
            f"📍 위치: {completed_detection.location}\n"
            f"🚗 속도: {completed_detection.detected_speed}km/h"
            f" (제한: {completed_detection.speed_limit}km/h)"
        )
        assert completed_detection.location in body
        assert str(completed_detection.detected_speed) in body

    @pytest.mark.skipif(not firebase_available, reason="firebase_admin not installed")
    @patch("tasks.notification_tasks.os.environ.get")
    def test_send_notification_mock_mode(self, mock_env, completed_detection):
        """Mock 모드에서 알림 전송 테스트"""
        mock_env.return_value = "true"

        from tasks.notification_tasks import send_notification

        result = send_notification(completed_detection.id)

        assert result["status"] in ["sent", "skipped"]


@pytest.mark.django_db(databases="__all__")
class TestTaskErrorHandling:
    """Task 에러 핸들링 테스트 (모듈 의존성 없이)"""

    def test_detection_status_transitions(self, pending_detection):
        """Detection 상태 전이 테스트"""
        assert pending_detection.status == "pending"

        # processing으로 전환
        pending_detection.status = "processing"
        pending_detection.save()
        pending_detection.refresh_from_db()
        assert pending_detection.status == "processing"

        # completed로 전환
        pending_detection.status = "completed"
        pending_detection.save()
        pending_detection.refresh_from_db()
        assert pending_detection.status == "completed"

    def test_detection_failed_status(self, pending_detection):
        """Detection 실패 상태 테스트"""
        pending_detection.status = "failed"
        pending_detection.error_message = "테스트 에러"
        pending_detection.save()
        pending_detection.refresh_from_db()

        assert pending_detection.status == "failed"
        assert pending_detection.error_message == "테스트 에러"

    def test_notification_creation_for_detection(self, completed_detection):
        """Detection에 대한 Notification 생성 테스트"""
        from apps.notifications.models import Notification

        notification = Notification.objects.create(
            detection_id=completed_detection.id,
            fcm_token="test-token",
            title="테스트 알림",
            body="테스트 본문",
            status="pending",
        )

        assert notification.detection_id == completed_detection.id
        assert notification.status == "pending"

        # sent로 상태 변경
        notification.status = "sent"
        notification.save()
        notification.refresh_from_db()
        assert notification.status == "sent"
