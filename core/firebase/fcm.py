"""Firebase Cloud Messaging Client"""

import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Firebase 초기화 상태
_firebase_initialized = False


def initialize_firebase():
    """Firebase Admin SDK 초기화"""
    global _firebase_initialized

    if _firebase_initialized:
        return

    import firebase_admin
    from firebase_admin import credentials

    if firebase_admin._apps:
        _firebase_initialized = True
        return

    # FIREBASE_CREDENTIALS 환경변수 우선
    cred_path = os.getenv("FIREBASE_CREDENTIALS")
    if cred_path and os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        logger.info(f"Firebase initialized with credentials: {cred_path}")
    else:
        # GOOGLE_APPLICATION_CREDENTIALS 사용
        firebase_admin.initialize_app()
        logger.info("Firebase initialized with default credentials")

    _firebase_initialized = True


class FCMClient:
    """FCM 클라이언트"""

    def __init__(self):
        initialize_firebase()

    def send_to_token(
        self, token: str, title: str, body: str, data: Optional[Dict[str, str]] = None
    ) -> str:
        """단일 토큰에 알림 전송"""
        from firebase_admin import messaging

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            token=token,
        )

        response = messaging.send(message)
        logger.info(f"FCM sent to token: {response}")
        return response

    def send_to_tokens(
        self,
        tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None,
    ) -> Dict:
        """여러 토큰에 알림 전송"""
        from firebase_admin import messaging

        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            tokens=tokens,
        )

        response = messaging.send_each_for_multicast(message)

        result = {
            "success_count": response.success_count,
            "failure_count": response.failure_count,
            "responses": [],
        }

        for idx, resp in enumerate(response.responses):
            if resp.success:
                result["responses"].append(
                    {
                        "token": tokens[idx],
                        "success": True,
                        "message_id": resp.message_id,
                    }
                )
            else:
                result["responses"].append(
                    {
                        "token": tokens[idx],
                        "success": False,
                        "error": str(resp.exception),
                    }
                )

        logger.info(
            f"FCM multicast: {response.success_count} success, "
            f"{response.failure_count} failed"
        )
        return result


# 편의 함수
_fcm_client = None


def get_fcm_client() -> FCMClient:
    global _fcm_client
    if _fcm_client is None:
        _fcm_client = FCMClient()
    return _fcm_client


def send_push_notification(
    token: str, title: str, body: str, data: Optional[Dict[str, str]] = None
) -> str:
    """푸시 알림 전송 (편의 함수)"""
    return get_fcm_client().send_to_token(token, title, body, data)
