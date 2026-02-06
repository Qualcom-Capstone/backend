"""OCR Worker Tasks (CPU 집약적)"""

import logging
import os
import re

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# Mock 모드 (테스트용)
OCR_MOCK = os.getenv("OCR_MOCK", "false").lower() == "true"

# EasyOCR Reader 캐싱 (Worker 프로세스 수준 싱글턴)
_ocr_reader = None


def get_ocr_reader():
    """EasyOCR Reader를 캐싱하여 모델 재로딩 방지 (prefork Worker당 1회)"""
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr

        _ocr_reader = easyocr.Reader(["ko", "en"], gpu=False)
        logger.info("EasyOCR Reader initialized")
    return _ocr_reader


def mock_ocr_result():
    """테스트용 가짜 OCR 결과 생성"""
    import random

    num1 = random.randint(10, 999)
    char = random.choice("가나다라마바사아자차카타파하")
    num2 = random.randint(1000, 9999)
    plate = f"{num1}{char}{num2}"
    confidence = random.uniform(0.85, 0.99)
    return plate, confidence


def is_valid_plate(text: str) -> bool:
    """한국 번호판 패턴 검증"""
    pattern = r"^\d{2,3}[가-힣]\d{4}$"
    return bool(re.match(pattern, text.replace(" ", "")))


def normalize_plate(text: str) -> str:
    """번호판 정규화 (공백 제거)"""
    return text.replace(" ", "").upper()


@shared_task(bind=True, max_retries=3, default_retry_delay=60, acks_late=True)
def process_ocr(self, detection_id: int, gcs_uri: str):
    """
    OCR 처리 Task
    - GCS에서 이미지 다운로드
    - EasyOCR 실행
    - 직접 MySQL 업데이트 (Choreography 패턴)
    - MSA: 각 서비스별 DB 사용
    """
    from apps.detections.models import Detection
    from apps.vehicles.models import Vehicle
    from tasks.notification_tasks import send_notification

    try:
        # 1. 상태를 processing으로 업데이트 (detections_db)
        Detection.objects.using("detections_db").filter(id=detection_id).update(
            status="processing", updated_at=timezone.now()
        )

        if OCR_MOCK:
            # Mock 모드: 실제 OCR 없이 가짜 결과 반환
            import random
            import time

            time.sleep(random.uniform(0.1, 0.5))
            plate_number, confidence = mock_ocr_result()
        else:
            # 실제 OCR 처리
            from core.gcs.client import download_image

            # 2. GCS에서 이미지 다운로드
            image_bytes = download_image(gcs_uri)

            # 3. EasyOCR 실행 (캐싱된 Reader 사용)
            reader = get_ocr_reader()
            results = reader.readtext(image_bytes)

            # 4. 번호판 파싱 (신뢰도 가장 높은 결과)
            plate_number = None
            confidence = 0.0

            for bbox, text, conf in results:
                if is_valid_plate(text) and conf > confidence:
                    plate_number = normalize_plate(text)
                    confidence = conf

        # 5. 직접 MySQL 업데이트 (detections_db)
        detection = Detection.objects.using("detections_db").get(id=detection_id)
        detection.ocr_result = plate_number
        detection.ocr_confidence = confidence
        detection.status = "completed"
        detection.processed_at = timezone.now()
        detection.save(
            using="detections_db",
            update_fields=[
                "ocr_result",
                "ocr_confidence",
                "status",
                "processed_at",
                "updated_at",
            ],
        )

        # 6. Vehicle 매칭 (MSA: vehicles_db에서 조회)
        if plate_number:
            try:
                vehicle = (
                    Vehicle.objects.using("vehicles_db")
                    .filter(plate_number=plate_number)
                    .first()
                )
                if vehicle:
                    detection.vehicle_id = vehicle.id
                    detection.save(
                        using="detections_db",
                        update_fields=["vehicle_id", "updated_at"],
                    )

                    # 7. FCM 토큰이 있으면 알림 Task 발행
                    if vehicle.fcm_token:
                        send_notification.apply_async(
                            args=[detection_id], queue="fcm_queue"
                        )
            except Exception as e:
                logger.warning(f"Vehicle lookup failed: {e}")

        logger.info(f"OCR completed for detection {detection_id}: {plate_number}")
        return {
            "detection_id": detection_id,
            "plate": plate_number,
            "confidence": confidence,
        }

    except Exception as exc:
        is_final_retry = self.request.retries >= self.max_retries
        if is_final_retry:
            # 최종 실패: status=failed 기록
            Detection.objects.using("detections_db").filter(id=detection_id).update(
                status="failed", error_message=str(exc), updated_at=timezone.now()
            )
            logger.error(f"OCR permanently failed for detection {detection_id}: {exc}")
            raise
        else:
            # 재시도 가능: processing 유지, 에러만 기록
            Detection.objects.using("detections_db").filter(id=detection_id).update(
                error_message=f"Retry {self.request.retries}: {exc}",
                updated_at=timezone.now(),
            )
            logger.warning(
                f"OCR retry {self.request.retries}/{self.max_retries} "
                f"for detection {detection_id}: {exc}"
            )
            raise self.retry(exc=exc)
