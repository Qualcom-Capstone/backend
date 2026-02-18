"""
AMQP Domain Event Publisher (Kombu)

Choreography 패턴에서 백엔드 서비스 간 도메인 이벤트 발행.
프로토콜 분리 원칙: IoT 경계는 MQTT, 서비스 간 이벤트는 AMQP.
"""

import json
import logging
import os

from kombu import Connection, Exchange

logger = logging.getLogger(__name__)

# 도메인 이벤트 교환기 (topic exchange: routing key 기반 선택적 구독)
DOMAIN_EVENTS_EXCHANGE = Exchange("domain_events", type="topic", durable=True)


def publish_event(routing_key: str, payload: dict):
    """
    AMQP 도메인 이벤트 발행

    Topic exchange를 사용하여 이벤트를 발행하면,
    관심 있는 서비스가 routing key 패턴으로 독립적으로 구독한다.

    Args:
        routing_key: 이벤트 라우팅 키 (예: "detections.completed")
        payload: 이벤트 페이로드
    """
    broker_url = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@rabbitmq:5672//")

    try:
        with Connection(broker_url) as conn:
            producer = conn.Producer()
            producer.publish(
                json.dumps(payload),
                exchange=DOMAIN_EVENTS_EXCHANGE,
                routing_key=routing_key,
                content_type="application/json",
                declare=[DOMAIN_EVENTS_EXCHANGE],
            )
        logger.info(f"Domain event published: {routing_key} -> {payload}")
    except Exception as e:
        logger.error(f"Failed to publish domain event {routing_key}: {e}")
        raise
