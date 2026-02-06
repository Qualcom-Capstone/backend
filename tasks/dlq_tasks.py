"""DLQ (Dead Letter Queue) Consumer Task"""

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, acks_late=True)
def process_dlq_message(self, *args, **kwargs):
    """
    DLQ 메시지 처리

    Dead Letter Queue로 라우팅된 실패 메시지를 로깅하고
    관련 Detection 상태를 업데이트합니다.
    """
    headers = self.request.headers or {}
    original_queue = headers.get("x-first-death-queue", "unknown")
    death_reason = headers.get("x-first-death-reason", "unknown")

    logger.error(
        f"DLQ message received: queue={original_queue}, "
        f"reason={death_reason}, args={args}, kwargs={kwargs}"
    )

    # Detection 상태 업데이트 시도
    detection_id = args[0] if args else kwargs.get("detection_id")
    if detection_id:
        try:
            from apps.detections.models import Detection

            Detection.objects.using("detections_db").filter(
                id=detection_id
            ).update(
                status="failed",
                error_message=f"DLQ: {death_reason} from {original_queue}",
                updated_at=timezone.now(),
            )
            logger.info(f"Detection {detection_id} marked as failed via DLQ")
        except Exception as e:
            logger.error(f"Failed to update detection {detection_id} from DLQ: {e}")
