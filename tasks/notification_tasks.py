"""Notification Worker Tasks (I/O 집약적)"""

import logging
import os

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# Mock 모드 (테스트용)
FCM_MOCK = os.getenv("FCM_MOCK", "false").lower() == "true"


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    acks_late=True,
)
def send_notification(self, detection_id: int):
    """
    FCM 푸시 알림 전송 Task
    - 대시보드 토픽 브로드캐스트 (모든 감지에 대해)
    - 매칭된 차량 개별 푸시 (차량 있는 경우)
    - MSA: 각 서비스별 DB에서 조회
    """
    from apps.detections.models import Detection
    from apps.notifications.models import Notification
    from apps.vehicles.models import Vehicle

    try:
        # 1. Detection 조회 (detections_db)
        detection = Detection.objects.using("detections_db").get(
            id=detection_id, status="completed"
        )

        # 2. 알림 메시지 생성
        title = f"⚠️ 과속 위반 감지: {detection.ocr_result or '미확인'}"
        body = (
            f"📍 위치: {detection.location or '알 수 없음'}\n"
            f"🚗 속도: {detection.detected_speed}km/h "
            f"(제한: {detection.speed_limit}km/h)"
        )
        data = {
            "detection_id": str(detection_id),
            "plate_number": detection.ocr_result or "",
            "speed": str(detection.detected_speed),
            "speed_limit": str(detection.speed_limit),
            "location": detection.location or "",
            "detected_at": detection.detected_at.isoformat(),
        }

        # 3. 대시보드 토픽으로 항상 전송 (중복 방지)
        topic_response = None
        already_sent_topic = (
            Notification.objects.using("notifications_db")
            .filter(
                detection_id=detection_id,
                fcm_token="topic:dashboard_alerts",
                status="sent",
            )
            .exists()
        )

        if not already_sent_topic:
            try:
                if FCM_MOCK:
                    topic_response = f"mock-topic-{detection_id}"
                else:
                    from core.firebase.fcm import send_topic_notification

                    topic_response = send_topic_notification(
                        "dashboard_alerts", title, body, data
                    )
                logger.info(
                    f"Dashboard topic notification sent for detection "
                    f"{detection_id}: {topic_response}"
                )
            except Exception as e:
                logger.warning(
                    f"Dashboard topic notification failed for detection "
                    f"{detection_id}: {e}"
                )

            # 4. 토픽 알림 이력 저장 (notifications_db)
            Notification.objects.using("notifications_db").create(
                detection_id=detection_id,
                fcm_token="topic:dashboard_alerts",
                title=title,
                body=body,
                status="sent" if topic_response else "failed",
                sent_at=timezone.now() if topic_response else None,
                error_message=None if topic_response else "Topic send failed",
            )
        else:
            topic_response = "already_sent"
            logger.info(
                f"Dashboard topic notification already sent for detection "
                f"{detection_id}, skipping"
            )

        # 5. 매칭된 차량에 개별 푸시 (기존 동작)
        vehicle = None
        if detection.vehicle_id:
            try:
                vehicle = Vehicle.objects.using("vehicles_db").get(
                    id=detection.vehicle_id
                )
            except Vehicle.DoesNotExist:
                logger.warning(f"Vehicle {detection.vehicle_id} not found")

        if vehicle and vehicle.fcm_token:
            try:
                if FCM_MOCK:
                    vehicle_response = f"mock-message-id-{detection_id}"
                else:
                    from core.firebase.fcm import send_push_notification

                    vehicle_response = send_push_notification(
                        token=vehicle.fcm_token,
                        title=title,
                        body=body,
                        data=data,
                    )

                Notification.objects.using("notifications_db").create(
                    detection_id=detection_id,
                    fcm_token=vehicle.fcm_token,
                    title=title,
                    body=body,
                    status="sent",
                    sent_at=timezone.now(),
                )
                logger.info(
                    f"Vehicle notification sent for detection "
                    f"{detection_id}: {vehicle_response}"
                )
            except Exception as e:
                logger.warning(
                    f"Vehicle notification failed for detection " f"{detection_id}: {e}"
                )
                Notification.objects.using("notifications_db").create(
                    detection_id=detection_id,
                    fcm_token=vehicle.fcm_token,
                    title=title,
                    body=body,
                    status="failed",
                    error_message=str(e),
                )

        return {
            "status": "sent",
            "topic": bool(topic_response),
            "vehicle": bool(vehicle and vehicle.fcm_token),
        }

    except Detection.DoesNotExist:
        logger.warning(f"Detection {detection_id} not found or not completed, retrying")
        raise self.retry(countdown=3, max_retries=3)

    except Exception as exc:
        try:
            from apps.notifications.models import Notification

            Notification.objects.using("notifications_db").create(
                detection_id=detection_id,
                status="failed",
                retry_count=self.request.retries,
                error_message=str(exc),
            )
        except Exception as db_err:
            logger.error(
                f"Failed to record notification failure for detection {detection_id}: {db_err}"
            )

        logger.error(f"Notification failed for detection {detection_id}: {exc}")
        raise
