"""
MQTT Subscriber for IoT Edge Device messages

IoT 디바이스(Raspberry Pi 카메라)에서 오는 MQTT 메시지만 처리.
프로토콜 분리 원칙: MQTT는 IoT 경계 전용, 서비스 간 이벤트는 AMQP.
"""

import json
import logging
import os

import paho.mqtt.client as mqtt
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)


class MQTTSubscriber:
    """
    RabbitMQ MQTT Plugin을 통해 IoT 디바이스 메시지를 수신하는 Subscriber

    구독 토픽:
    - detections/new : IoT 디바이스 → Detection 생성 → OCR 발행
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
        username = os.getenv("MQTT_USER", "")
        password = os.getenv("MQTT_PASS", "")
        self.client.username_pw_set(username, password)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        """MQTT 연결 시 IoT 토픽 구독"""
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
        """메시지 처리"""
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in MQTT message: {e}")
            return

        if msg.topic == "detections/new":
            self._handle_new_detection(payload)
        else:
            logger.warning(f"Unknown MQTT topic: {msg.topic}")

    def _handle_new_detection(self, payload):
        """
        detections/new: IoT 디바이스에서 새 감지 수신
        1. DB에 pending 레코드 즉시 생성 (데이터 손실 방지)
        2. OCR Task 발행 (AMQP)
        """
        try:
            logger.info(f"Received MQTT message: {payload.get('camera_id')}")

            from apps.detections.models import Detection
            from tasks.ocr_tasks import process_ocr

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

            process_ocr.apply_async(
                args=[detection.id],
                kwargs={"gcs_uri": payload["image_gcs_uri"]},
                queue="ocr_queue",
                priority=5,
            )

            logger.info(f"OCR task dispatched for detection {detection.id}")

        except KeyError as e:
            logger.error(f"Missing required field in MQTT message: {e}")
        except Exception as e:
            logger.error(f"Error processing new detection: {e}")

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
