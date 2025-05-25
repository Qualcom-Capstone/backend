import os, json, logging
from celery import shared_task, Task
from celery.exceptions import Reject
from django.db import IntegrityError
from .models import NotificationLog, DeviceToken

import firebase_admin
from firebase_admin import messaging, credentials
from firebase_admin import exceptions as firebase_exceptions

# ──────────────── 0. 환경 설정 ─────────────────
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
    autoretry_for = (Exception,)
    retry_kwargs = {"max_retries": 3, "countdown": 5}
    retry_backoff = True
    retry_jitter = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error("Task %s failed permanently: %s", task_id, exc)
        raise Reject(exc, requeue=False)

# ──────────────── 2. 과속 차량 알림 태스크 ───────────────
@shared_task(bind=True, base=BaseRetryTask, acks_late=True)
def send_speeding_alert(self, payload: dict):
    title = "🚨 과속 차량 감지"
    body = f"{payload['car_number']} - {payload['car_speed']} km/h"

    tokens = list(
        DeviceToken.objects
        .values_list("token", flat=True)
    )

    if not tokens:
        logger.warning("⚠️ 알림 전송 대상 토큰이 없습니다.")
        return {"status": "NO_TARGETS"}

    success_count = 0
    failed_tokens = []

    # 공통 메시지 요소 사전 정의
    notification = messaging.Notification(title=title, body=body)
    data = {k: str(v) for k, v in payload.items()}

    INVALID_TOKEN_ERRORS = (
        messaging.UnregisteredError,
        firebase_exceptions.InvalidArgumentError,
    )

    for token in tokens:
        try:
            message = messaging.Message(
                notification=notification,
                data=data,
                token=token,
            )
            response = messaging.send(message)
            success_count += 1
            logger.info(f"✅ Sent to {token}: {response}")
        except INVALID_TOKEN_ERRORS as e:
            DeviceToken.objects.filter(token=token)
            logger.warning(f"🔕 Invalid token {token} 비활성화됨: {e}")
        except Exception as e:
            logger.error(f"❌ Failed to send to {token}: {e}")
            failed_tokens.append({
                "token": token,
                "error": str(e),
            })

    # 결과 기록
    try:
        NotificationLog.objects.create(
            car_data_id=payload["id"],
            status="PARTIAL_FAIL" if failed_tokens else "SUCCESS",
            response=json.dumps({
                "success_count": success_count,
                "failed_tokens": failed_tokens,
            })
        )
    except IntegrityError:
        logger.warning("CarData %s not ready for logging", payload["id"])

    return {
        "total": len(tokens),
        "success": success_count,
        "fail": len(failed_tokens)
    }
