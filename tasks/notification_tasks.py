"""Notification Worker Tasks (I/O 집약적)"""
import os
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# Mock 모드 (테스트용)
FCM_MOCK = os.getenv('FCM_MOCK', 'false').lower() == 'true'


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    acks_late=True
)
def send_notification(self, detection_id: int):
    """
    FCM 푸시 알림 전송 Task
    - Exponential Backoff 재시도
    - MSA: 각 서비스별 DB에서 조회
    """
    from apps.detections.models import Detection
    from apps.vehicles.models import Vehicle
    from apps.notifications.models import Notification

    try:
        # 1. Detection 조회 (detections_db)
        detection = Detection.objects.using('detections_db').get(
            id=detection_id,
            status='completed'
        )
        
        # 2. Vehicle 조회 (vehicles_db) - MSA: 별도 DB
        vehicle = None
        if detection.vehicle_id:
            try:
                vehicle = Vehicle.objects.using('vehicles_db').get(id=detection.vehicle_id)
            except Vehicle.DoesNotExist:
                logger.warning(f"Vehicle {detection.vehicle_id} not found")
        
        if not vehicle or not vehicle.fcm_token:
            logger.warning(f"No FCM token for detection {detection_id}")
            return {'status': 'skipped', 'reason': 'No FCM token'}
        
        # 3. FCM 메시지 생성
        title = f"⚠️ 과속 위반 감지: {detection.ocr_result}"
        body = (
            f"📍 위치: {detection.location}\n"
            f"🚗 속도: {detection.detected_speed}km/h "
            f"(제한: {detection.speed_limit}km/h)"
        )
        
        if FCM_MOCK:
            # Mock 모드
            import time
            import random
            time.sleep(random.uniform(0.05, 0.1))
            response = f"mock-message-id-{detection_id}"
        else:
            # 실제 FCM 전송
            import firebase_admin
            from firebase_admin import messaging, credentials
            
            # Firebase 초기화 (최초 1회)
            if not firebase_admin._apps:
                cred_path = os.getenv('FIREBASE_CREDENTIALS')
                if cred_path:
                    cred = credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
                else:
                    # GOOGLE_APPLICATION_CREDENTIALS 사용
                    firebase_admin.initialize_app()
            
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                data={
                    'detection_id': str(detection_id),
                    'plate_number': detection.ocr_result or '',
                    'speed': str(detection.detected_speed),
                    'speed_limit': str(detection.speed_limit),
                    'location': detection.location or '',
                    'detected_at': detection.detected_at.isoformat()
                },
                token=vehicle.fcm_token
            )
            
            # 4. FCM API 호출
            response = messaging.send(message)
        
        # 5. 성공 이력 저장 (notifications_db)
        Notification.objects.using('notifications_db').create(
            detection_id=detection_id,
            fcm_token=vehicle.fcm_token,
            title=title,
            body=body,
            status='sent',
            sent_at=timezone.now()
        )
        
        logger.info(f"Notification sent for detection {detection_id}: {response}")
        return {'status': 'sent', 'fcm_response': response}
        
    except Detection.DoesNotExist:
        logger.error(f"Detection {detection_id} not found")
        return {'status': 'error', 'reason': 'Detection not found'}
    
    except Exception as exc:
        # FCM 실패 시 이력 저장 후 재시도
        try:
            Notification.objects.using('notifications_db').create(
                detection_id=detection_id,
                status='failed',
                retry_count=self.request.retries,
                error_message=str(exc)
            )
        except Exception:
            pass
        
        logger.error(f"Notification failed for detection {detection_id}: {exc}")
        raise
