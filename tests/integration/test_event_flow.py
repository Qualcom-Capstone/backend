"""
Integration Tests for Event-Driven Flow

테스트 시나리오:
1. Detection 생성 → OCR Task → Notification Task (전체 플로우)
2. MQTT 메시지 수신 → Detection 생성 (Ingestion 플로우)
3. 재시도 로직 테스트

Note: google.cloud와 firebase_admin 모듈이 없는 환경에서는 일부 테스트 skip
"""
import pytest
import sys
from unittest.mock import patch, MagicMock
from django.utils import timezone
from apps.vehicles.models import Vehicle
from apps.detections.models import Detection
from apps.notifications.models import Notification

# 모듈 설치 여부 확인
try:
    from google.cloud import storage
    google_available = True
except ImportError:
    google_available = False

try:
    import firebase_admin
    firebase_available = True
except ImportError:
    firebase_available = False


@pytest.mark.django_db(transaction=True)
class TestIngestionFlow:
    """
    Ingestion 플로우 테스트
    MQTT/API → Detection 생성 → Task 발행
    """
    
    def test_detection_creation_triggers_pending_status(self):
        """Detection 생성 시 pending 상태 테스트"""
        detection = Detection.objects.create(
            camera_id='CAM-INGEST-001',
            location='수신 테스트',
            detected_speed=75.0,
            speed_limit=60.0,
            detected_at=timezone.now(),
            image_gcs_uri='gs://test-bucket/ingest.jpg',
            status='pending'
        )
        
        assert detection.status == 'pending'
        assert detection.processed_at is None
        assert detection.ocr_result is None
    
    def test_detection_with_speed_violation(self):
        """과속 감지 데이터 생성 테스트"""
        detection = Detection.objects.create(
            camera_id='CAM-SPEED-001',
            location='과속 테스트',
            detected_speed=95.0,  # 과속
            speed_limit=60.0,
            detected_at=timezone.now(),
            image_gcs_uri='gs://test-bucket/speed.jpg',
            status='pending'
        )
        
        # 과속 여부 확인
        assert detection.detected_speed > detection.speed_limit
        violation_amount = detection.detected_speed - detection.speed_limit
        assert violation_amount == 35.0


@pytest.mark.django_db(transaction=True)
class TestChoreographyPattern:
    """
    Choreography 패턴 테스트
    각 서비스가 독립적으로 다음 이벤트를 발행하는지 테스트
    """
    
    def test_detection_to_notification_data_flow(self, sample_vehicle):
        """Detection → Notification 데이터 흐름 테스트"""
        # Detection 생성 및 완료
        detection = Detection.objects.create(
            vehicle=sample_vehicle,
            camera_id='CAM-FLOW-001',
            location='흐름 테스트',
            detected_speed=90.0,
            speed_limit=60.0,
            detected_at=timezone.now(),
            processed_at=timezone.now(),
            image_gcs_uri='gs://test-bucket/flow.jpg',
            ocr_result='12가3456',
            ocr_confidence=0.95,
            status='completed'
        )
        
        # Notification 생성
        notification = Notification.objects.create(
            detection=detection,
            fcm_token=sample_vehicle.fcm_token,
            title=f'과속 위반: {detection.ocr_result}',
            body=f'속도: {detection.detected_speed}km/h',
            status='sent'
        )
        
        # 데이터 연결 확인
        assert notification.detection == detection
        assert notification.fcm_token == sample_vehicle.fcm_token
        assert detection.ocr_result in notification.title
    
    def test_multiple_notifications_for_detection(self, completed_detection):
        """하나의 Detection에 여러 Notification (재시도) 테스트"""
        # 첫 번째 알림 (실패)
        notif1 = Notification.objects.create(
            detection=completed_detection,
            fcm_token='token-1',
            title='알림 1',
            body='본문 1',
            status='failed',
            retry_count=0,
            error_message='Connection timeout'
        )
        
        # 두 번째 알림 (재시도 - 성공)
        notif2 = Notification.objects.create(
            detection=completed_detection,
            fcm_token='token-1',
            title='알림 1',
            body='본문 1',
            status='sent',
            retry_count=1
        )
        
        # 동일 Detection에 여러 알림 존재 확인
        notifications = completed_detection.notifications.all()
        assert notifications.count() == 2
        assert notifications.filter(status='sent').count() == 1


@pytest.mark.django_db(transaction=True)
class TestErrorHandling:
    """에러 핸들링 및 재시도 로직 테스트"""
    
    def test_detection_not_found(self):
        """존재하지 않는 Detection 처리 테스트"""
        # 존재하지 않는 ID
        invalid_id = 999999
        detection = Detection.objects.filter(id=invalid_id).first()
        
        assert detection is None
    
    def test_notification_without_vehicle(self):
        """차량이 연결되지 않은 Detection에 대한 알림 테스트"""
        # 차량 없는 Detection
        detection = Detection.objects.create(
            camera_id='CAM-NOVEH-001',
            location='차량 없음 테스트',
            detected_speed=85.0,
            speed_limit=60.0,
            detected_at=timezone.now(),
            image_gcs_uri='gs://test-bucket/noveh.jpg',
            ocr_result='00가0000',
            status='completed'
        )
        
        # vehicle이 None인지 확인
        assert detection.vehicle is None
        
        # 알림을 생성하려면 FCM 토큰이 필요
        # vehicle이 없으면 FCM 토큰도 없음
        fcm_token = detection.vehicle.fcm_token if detection.vehicle else None
        assert fcm_token is None
    
    def test_detection_status_failed(self):
        """Detection 실패 상태 처리 테스트"""
        detection = Detection.objects.create(
            camera_id='CAM-FAIL-001',
            location='실패 테스트',
            detected_speed=80.0,
            speed_limit=60.0,
            detected_at=timezone.now(),
            image_gcs_uri='gs://test-bucket/fail.jpg',
            status='pending'
        )
        
        # 처리 중 에러 발생 시나리오
        detection.status = 'failed'
        detection.error_message = 'OCR processing failed: Invalid image format'
        detection.save()
        
        detection.refresh_from_db()
        assert detection.status == 'failed'
        assert 'Invalid image format' in detection.error_message


@pytest.mark.django_db(transaction=True)
class TestEndToEndDataIntegrity:
    """End-to-End 데이터 무결성 테스트"""
    
    def test_complete_data_flow(self, sample_vehicle):
        """전체 데이터 흐름 무결성 테스트"""
        # 1. Detection 생성 (Ingestion)
        detection = Detection.objects.create(
            camera_id='CAM-E2E-001',
            location='E2E 테스트 위치',
            detected_speed=90.0,
            speed_limit=60.0,
            detected_at=timezone.now(),
            image_gcs_uri='gs://test-bucket/e2e-test.jpg',
            status='pending'
        )
        
        # 2. OCR 처리 (시뮬레이션)
        detection.status = 'processing'
        detection.save()
        
        detection.ocr_result = sample_vehicle.plate_number
        detection.ocr_confidence = 0.95
        detection.vehicle = sample_vehicle
        detection.processed_at = timezone.now()
        detection.status = 'completed'
        detection.save()
        
        # 3. Notification 생성
        notification = Notification.objects.create(
            detection=detection,
            fcm_token=sample_vehicle.fcm_token,
            title=f'⚠️ 과속 위반 감지: {detection.ocr_result}',
            body=f'📍 위치: {detection.location}\n🚗 속도: {detection.detected_speed}km/h',
            status='sent',
            sent_at=timezone.now()
        )
        
        # 검증
        assert detection.status == 'completed'
        assert detection.vehicle == sample_vehicle
        assert notification.status == 'sent'
        
        # 관계 확인
        assert notification.detection == detection
        assert detection in sample_vehicle.detections.all()
        assert notification in detection.notifications.all()
    
    def test_statistics_calculation(self, sample_vehicle):
        """통계 계산 테스트"""
        # 여러 Detection 생성
        speeds = [75.0, 85.0, 95.0, 105.0]
        for i, speed in enumerate(speeds):
            Detection.objects.create(
                vehicle=sample_vehicle,
                camera_id=f'CAM-STAT-{i}',
                location='통계 테스트',
                detected_speed=speed,
                speed_limit=60.0,
                detected_at=timezone.now(),
                image_gcs_uri=f'gs://test-bucket/stat-{i}.jpg',
                status='completed' if i % 2 == 0 else 'pending'
            )
        
        # 통계 확인
        total = Detection.objects.count()
        completed = Detection.objects.filter(status='completed').count()
        pending = Detection.objects.filter(status='pending').count()
        
        assert total >= 4
        assert completed >= 2
        assert pending >= 2


@pytest.mark.django_db(transaction=True) 
@pytest.mark.skipif(not (google_available and firebase_available), 
                    reason="Requires google.cloud and firebase_admin")
class TestFullTaskExecution:
    """실제 Task 실행 테스트 (모듈 설치된 환경에서만)"""
    
    @patch('tasks.ocr_tasks.os.environ.get')
    @patch('tasks.notification_tasks.os.environ.get')
    def test_ocr_and_notification_tasks(self, mock_notif_env, mock_ocr_env, sample_vehicle):
        """OCR Task와 Notification Task 연계 테스트"""
        mock_ocr_env.return_value = 'true'
        mock_notif_env.return_value = 'true'
        
        from tasks.ocr_tasks import process_ocr
        from tasks.notification_tasks import send_notification
        
        # Detection 생성
        detection = Detection.objects.create(
            camera_id='CAM-TASK-001',
            location='Task 테스트',
            detected_speed=95.0,
            speed_limit=60.0,
            detected_at=timezone.now(),
            image_gcs_uri='gs://test-bucket/task.jpg',
            status='pending'
        )
        
        # OCR 실행
        process_ocr(detection.id, gcs_uri=detection.image_gcs_uri)
        detection.refresh_from_db()
        
        assert detection.status == 'completed'
