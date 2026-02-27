"""MQTT Subscriber for Edge Device messages"""

import json
import logging
import os

import paho.mqtt.client as mqtt
from django.db import close_old_connections
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)


class MQTTSubscriber:
    """
    RabbitMQ MQTT Plugin을 통해 Edge Device 메시지를 수신하는 Subscriber

    Flow:
    1. Raspberry Pi -> MQTT Publish (detections/new)
    2. RabbitMQ MQTT Plugin -> 내부 변환
    3. Django MQTT Subscriber -> 메시지 수신
    4. Detection 생성 (pending) -> OCR Task 발행
    """

    def __init__(self):
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            protocol=mqtt.MQTTv311,
            client_id=f"django-main-{os.getpid()}",
        )
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

        # 인증 설정
        username = os.getenv("MQTT_USER", "sa")
        password = os.getenv("MQTT_PASS", "1234")
        self.client.username_pw_set(username, password)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        """MQTT 연결 시 토픽 구독"""
        if reason_code.is_failure:
            logger.error(f"MQTT connection failed: {reason_code}")
        else:
            logger.info("Connected to MQTT broker")
            client.subscribe("detections/new", qos=1)

    def on_disconnect(
        self, client, userdata, disconnect_flags, reason_code, properties
    ):
        """연결 끊김 처리"""
        if reason_code.is_failure:
            logger.warning(
                f"Unexpected MQTT disconnect: {reason_code}, reconnecting..."
            )

    def on_message(self, client, userdata, msg):
        """
        메시지 수신 시 처리
        1. DB에 pending 레코드 즉시 생성 (데이터 손실 방지)
        2. OCR Task 발행
        """
        try:
            payload = json.loads(msg.payload.decode())
            logger.info(f"Received MQTT message: {payload.get('camera_id')}")

            # 장기 실행 스레드에서 stale DB 연결 방지
            close_old_connections()

            # Import here to avoid circular imports
            from apps.detections.models import Detection
            from tasks.ocr_tasks import process_ocr

            # 1. Detection 레코드 생성 (status=pending, detections_db)
            detection = Detection.objects.using("detections_db").create(
                camera_id=payload.get("camera_id"),
                location=payload.get("location"),
                detected_speed=payload["detected_speed"],
                speed_limit=payload.get("speed_limit", 60.0),
                detected_at=self._parse_detected_at(payload.get("detected_at")),
                image_gcs_uri=payload["image_gcs_uri"],
                status="pending",
            )

            logger.info(f"Detection {detection.id} created (pending)")

            # 2. OCR Task 발행 (AMQP via Celery)
            process_ocr.apply_async(
                args=[detection.id],
                kwargs={"gcs_uri": payload["image_gcs_uri"]},
                queue="ocr_queue",
                priority=5,
            )

            logger.info(f"OCR task dispatched for detection {detection.id}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in MQTT message: {e}")
        except KeyError as e:
            logger.error(f"Missing required field in MQTT message: {e}")
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")

    @staticmethod
    def _parse_detected_at(value):
        """detected_at 문자열을 datetime으로 파싱"""
        if value is None:
            return timezone.now()
        if isinstance(value, str):
            parsed = parse_datetime(value)
            if parsed is None:
                logger.warning(
                    f"Invalid detected_at format: {value}, using current time"
                )
                return timezone.now()
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed)
            return parsed
        return value

    def start(self):
        """MQTT Subscriber 시작 (blocking)"""
        host = os.getenv("RABBITMQ_HOST", "rabbitmq")
        port = int(os.getenv("MQTT_PORT", 1883))

        logger.info(f"Connecting to MQTT broker at {host}:{port}")

        try:
            self.client.connect(host, port, keepalive=60)
            self.client.loop_forever()
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            raise

    def stop(self):
        """MQTT Subscriber 종료"""
        self.client.disconnect()
        logger.info("MQTT Subscriber stopped")


def start_mqtt_subscriber(blocking=True):
    """
    MQTT Subscriber 시작

    Args:
        blocking: True면 현재 스레드에서 블로킹 실행,
                  False면 daemon 스레드에서 백그라운드 실행
    """
    subscriber = MQTTSubscriber()
    if blocking:
        subscriber.start()
    else:
        import threading

        thread = threading.Thread(target=subscriber.start, daemon=True)
        thread.start()
        logger.info("MQTT Subscriber started in background thread")
    return subscriber
