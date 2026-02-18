"""
AMQP Domain Event Consumer (Kombu)

Alert Service가 도메인 이벤트를 직접 구독하여 자율적으로 처리.
Choreography: 각 서비스는 이벤트에 독립적으로 반응한다.

Main Service를 거치지 않고 Alert Service가 직접
detections.completed 이벤트를 구독하여 알림 발송 여부를 결정한다.
"""

import json
import logging
import os
import time

from kombu import Connection, Exchange, Queue
from kombu.mixins import ConsumerMixin

logger = logging.getLogger(__name__)

DOMAIN_EVENTS_EXCHANGE = Exchange("domain_events", type="topic", durable=True)


class AlertEventConsumer(ConsumerMixin):
    """
    Alert Service 도메인 이벤트 소비자

    detections.completed 이벤트를 구독하고,
    Alert Service가 자율적으로 알림 발송 여부를 결정한다.
    OCR Service의 존재도, Main Service의 중개도 모른다.
    """

    def __init__(self, connection):
        self.connection = connection

    def get_consumers(self, Consumer, channel):
        queue = Queue(
            "alert_domain_events",
            exchange=DOMAIN_EVENTS_EXCHANGE,
            routing_key="detections.completed",
            durable=True,
            queue_arguments={
                "x-dead-letter-exchange": "dlq_exchange",
            },
        )
        return [
            Consumer(
                queues=[queue],
                callbacks=[self.on_event],
                accept=["json"],
            )
        ]

    def on_event(self, body, message):
        """도메인 이벤트 수신 및 처리"""
        try:
            payload = json.loads(body) if isinstance(body, str) else body
            routing_key = message.delivery_info.get("routing_key", "")

            if routing_key == "detections.completed":
                self._on_detection_completed(payload)

            message.ack()
        except Exception as e:
            logger.error(f"Failed to process domain event: {e}")
            message.reject(requeue=False)

    def _on_detection_completed(self, payload):
        """
        detections.completed 이벤트에 반응

        Alert Service의 자율적 판단:
        "OCR이 완료됐으니 알림을 보내야겠다"
        """
        detection_id = payload["detection_id"]
        logger.info(
            f"Detection {detection_id} completed event received — "
            f"processing notification"
        )

        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                from tasks.notification_tasks import process_notification

                process_notification(detection_id)
                return
            except Exception as e:
                if "DoesNotExist" in type(e).__name__ and attempt < max_retries:
                    logger.warning(
                        f"Detection {detection_id} not ready, "
                        f"retry {attempt + 1}/{max_retries}"
                    )
                    time.sleep(3)
                else:
                    raise


def start_event_consumer():
    """Alert Service 도메인 이벤트 소비자 시작 (blocking)"""
    broker_url = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672//")
    logger.info(f"Starting Alert Event Consumer on {broker_url}")

    with Connection(broker_url) as conn:
        consumer = AlertEventConsumer(conn)
        consumer.run()
