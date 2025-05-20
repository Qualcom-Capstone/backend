# tasks.py
import os, json, logging
from celery import shared_task, Task
from celery.exceptions import Reject
from django.db import IntegrityError
from .models import NotificationLog

import firebase_admin
from firebase_admin import messaging, credentials

logger = logging.getLogger(__name__)

# ──────────────── 0. Firebase Admin 초기화 ─────────────────
if not firebase_admin._apps:
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_path:
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS 환경 변수가 설정되지 않았습니다.")
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

# ──────────────── 1. Base Task (DLQ + Retry) ───────────────
class BaseRetryTask(Task):
    autoretry_for  = (Exception,)
    retry_kwargs   = {"max_retries": 3, "countdown": 5}
    retry_backoff  = True
    retry_jitter   = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error("Task %s failed permanently: %s", task_id, exc)
        raise Reject(exc, requeue=False)

# ──────────────── 2. 과속 차량 알림 태스크 ───────────────
@shared_task(bind=True, base=BaseRetryTask, acks_late=True)
def send_speeding_alert(self, payload: dict):
    """
    payload = {
        "id":         <int>,      # CarData PK
        "timestamp":  <ISO8601>,
        "car_number": <str>,
        "car_speed":  <int|float>,
    }
    """
    title = "🚨 과속 차량 감지"
    body  = f"{payload['car_number']} - {payload['car_speed']} km/h"

    try:
        # 2-1. FCM 메시지 객체 구성
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            data={k: str(v) for k, v in payload.items()},
            topic="traffic-monitor"
        )

        # 2-2. 메시지 전송
        response = messaging.send(message)

        # 2-3. 성공 로그 저장
        NotificationLog.objects.create(
            car_data_id=payload["id"],
            status="SUCCESS",
            response=json.dumps({"message_id": response})
        )
        return {"message_id": response}

    except Exception as exc:
        # 2-4. 실패시 로그 → 재시도
        try:
            NotificationLog.objects.create(
                car_data_id=payload["id"],
                status="RETRY",
                response=str(exc),
            )
        except IntegrityError:
            logger.warning("CarData %s not yet ready for logging", payload["id"])
        raise self.retry(exc=exc, countdown=10)
