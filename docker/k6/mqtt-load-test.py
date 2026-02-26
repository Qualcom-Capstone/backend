#!/usr/bin/env python3
"""
MQTT 파이프라인 부하테스트 - IoT 카메라 시뮬레이션

실제 사용 패턴 기반 시나리오:
  - normal: 정상 운영 (20대 카메라, 1건/분)
  - rush_hour: 러시아워 (20대 카메라, 5건/분)
  - burst: 버스트 스톰 (10대 카메라, 1건/초)

파이프라인 검증:
  MQTT 발행 → Detection(pending) → OCR Worker → Alert Worker → 완료

인프라 기준: 8x GCP 인스턴스 (OCR Worker 3대 확장)
  - speedcam-app (e2-small): Django + Gunicorn + MQTT Subscriber
  - speedcam-db (e2-medium): MySQL 8.0
  - speedcam-mq (e2-small): RabbitMQ (MQTT + AMQP)
  - speedcam-ocr (e2-small): Celery OCR Worker (concurrency=1)
  - speedcam-ocr-2 (e2-medium): Celery OCR Worker (concurrency=2)
  - speedcam-ocr-3 (e2-medium): Celery OCR Worker (concurrency=2)
  - speedcam-alert (e2-small): Kombu Consumer + Celery gevent Worker
  - speedcam-mon (e2-small): Prometheus + Grafana + Loki + Jaeger
  총 OCR 동시 처리: 5 (1 + 2 + 2)
가설 기반 검증 (load-test-plan.md 참조)
"""

import argparse
import json
import os
import random
import signal
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: paho-mqtt 패키지가 필요합니다. 설치: pip3 install paho-mqtt")
    sys.exit(1)

try:
    import requests
except ImportError:
    requests = None
    print("WARNING: requests 패키지 없음. 파이프라인 검증 비활성화 (pip3 install requests)")

# ============================================================
# 시나리오 정의
# ============================================================
SCENARIOS = {
    'normal': {
        'description': '정상 운영: 20대 카메라, 1건/분 (0.33 msg/s)',
        'workers': 20,
        'rate_per_worker': 1 / 60,  # 분당 1건
        'duration': 120,
        'expected_total': 40,
        'hypothesis': {
            'publish_success': '100%',
            'completion_rate': '100%',
            'completion_time': '60초 이내',
            'peak_ocr_queue': '< 5',
            'dlq_messages': '0',
            'bottleneck': '없음',
        },
    },
    'rush_hour': {
        'description': '러시아워: 20대 카메라, 5건/분 (1.67 msg/s)',
        'workers': 20,
        'rate_per_worker': 5 / 60,  # 분당 5건
        'duration': 120,
        'expected_total': 200,
        'hypothesis': {
            'publish_success': '100%',
            'completion_rate': '95%+ (120초 이내)',
            'completion_time': '120초 이내',
            'peak_ocr_queue': '< 10 (mock) / < 30 (실제 EasyOCR)',
            'dlq_messages': '0',
            'bottleneck': 'OCR worker (mock 느린 경우)',
        },
    },
    'burst': {
        'description': '버스트 스톰: 10대 카메라, 1건/초 (10 msg/s)',
        'workers': 10,
        'rate_per_worker': 1.0,  # 초당 1건
        'duration': 60,
        'expected_total': 600,
        'hypothesis': {
            'publish_success': '100%',
            'completion_rate': '100% (300초 이내)',
            'completion_time': '300초 이내',
            'peak_ocr_queue': '< 500 (실제 EasyOCR 기준)',
            'dlq_messages': '0',
            'bottleneck': 'OCR Worker 처리 속도 (실제 EasyOCR 기준, concurrency=5)',
        },
    },
}

# 카메라 위치 데이터 (시뮬레이션용)
LOCATIONS = [
    "서울시 강남구 테헤란로",
    "서울시 서초구 반포대로",
    "서울시 송파구 올림픽로",
    "경기도 성남시 분당구 판교역로",
    "인천시 연수구 송도대로",
    "서울시 마포구 월드컵북로",
    "서울시 영등포구 여의대방로",
    "부산시 해운대구 해운대로",
    "대구시 수성구 동대구로",
    "광주시 서구 상무대로",
]

CAMERA_IDS = [f"CAM-{str(i).zfill(3)}" for i in range(1, 21)]
TOPIC = "detections/new"

# 종료 플래그
shutdown_event = threading.Event()


# ============================================================
# 파이프라인 검증기
# ============================================================
class PipelineVerifier:
    """파이프라인 완료 검증 - /api/v1/detections/statistics/ 활용"""

    def __init__(self, api_base_url, rabbitmq_api_url=None,
                 rabbitmq_user='sa', rabbitmq_pass=''):
        self.api_base_url = api_base_url.rstrip('/')
        self.rabbitmq_api_url = rabbitmq_api_url.rstrip('/') if rabbitmq_api_url else None
        self.rabbitmq_auth = (rabbitmq_user, rabbitmq_pass)
        self.available = requests is not None
        self.peak_ocr_queue = 0
        self.peak_fcm_queue = 0

    def get_detection_stats(self):
        """GET /api/v1/detections/statistics/ - 집계 통계 조회

        Returns:
            dict: {total_detections, completed_count, failed_count,
                   pending_count, avg_speed, max_speed}
        """
        if not self.available:
            return None
        try:
            resp = requests.get(
                f"{self.api_base_url}/api/v1/detections/statistics/",
                timeout=10
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"  [검증] 통계 조회 실패: {e}")
            return None

    def get_queue_depth(self):
        """RabbitMQ Management API로 큐 깊이 조회 (HTTP Basic Auth)"""
        if not self.available or not self.rabbitmq_api_url:
            return {}
        try:
            resp = requests.get(
                f"{self.rabbitmq_api_url}/api/queues/%2F",
                auth=self.rabbitmq_auth,
                timeout=5
            )
            resp.raise_for_status()
            queues = resp.json()
            result = {}
            for q in queues:
                name = q.get('name', '')
                if name in ('ocr_queue', 'fcm_queue', 'dlq_queue'):
                    depth = q.get('messages', 0)
                    result[name] = depth
            return result
        except Exception as e:
            print(f"  [검증] 큐 깊이 조회 실패: {e}")
            return {}

    def get_notification_count(self):
        """GET /api/v1/notifications/ - 알림 카운트로 Alert Worker 동작 간접 검증"""
        if not self.available:
            return None
        try:
            resp = requests.get(
                f"{self.api_base_url}/api/v1/notifications/",
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get('count', len(data.get('results', [])))
        except Exception:
            return None

    def wait_for_completion(self, expected_count, baseline_stats,
                            timeout=300, poll_interval=5):
        """파이프라인 완료 대기 - /api/v1/detections/statistics/ 폴링

        baseline_stats와의 차이로 이번 테스트의 신규 감지만 카운트
        """
        if not self.available or baseline_stats is None:
            return None

        baseline_completed = baseline_stats.get('completed_count', 0)
        baseline_failed = baseline_stats.get('failed_count', 0)
        baseline_notifications = self.get_notification_count() or 0

        start_time = time.time()
        last_print = 0

        print(f"\n  [파이프라인 검증] {expected_count}건 완료 대기 중 (타임아웃: {timeout}초)")

        while time.time() - start_time < timeout:
            if shutdown_event.is_set():
                break

            current = self.get_detection_stats()
            if current is None:
                time.sleep(poll_interval)
                continue

            new_completed = current.get('completed_count', 0) - baseline_completed
            new_failed = current.get('failed_count', 0) - baseline_failed
            new_done = new_completed + new_failed
            new_pending = max(0, expected_count - new_done)

            # 큐 깊이 추적
            queue_depth = self.get_queue_depth()
            ocr_depth = queue_depth.get('ocr_queue', 0)
            fcm_depth = queue_depth.get('fcm_queue', 0)
            self.peak_ocr_queue = max(self.peak_ocr_queue, ocr_depth)
            self.peak_fcm_queue = max(self.peak_fcm_queue, fcm_depth)

            elapsed = time.time() - start_time
            if elapsed - last_print >= 10:
                notif_count = (self.get_notification_count() or 0) - baseline_notifications
                print(f"  [{elapsed:.0f}s] 완료: {new_completed} | 실패: {new_failed} | "
                      f"대기: {new_pending} | OCR큐: {ocr_depth} | FCM큐: {fcm_depth} | "
                      f"알림: {notif_count}")
                last_print = elapsed

            if new_done >= expected_count:
                completion_time = time.time() - start_time
                final_notif = (self.get_notification_count() or 0) - baseline_notifications
                return {
                    'completed': new_completed,
                    'failed': new_failed,
                    'pending': new_pending,
                    'completion_time_s': round(completion_time, 1),
                    'peak_ocr_queue': self.peak_ocr_queue,
                    'peak_fcm_queue': self.peak_fcm_queue,
                    'dlq_messages': queue_depth.get('dlq_queue', 0),
                    'notification_count': final_notif,
                }

            time.sleep(poll_interval)

        # 타임아웃
        current = self.get_detection_stats()
        final_completed = (current.get('completed_count', 0) - baseline_completed) if current else 0
        final_failed = (current.get('failed_count', 0) - baseline_failed) if current else 0

        final_notif = (self.get_notification_count() or 0) - baseline_notifications
        return {
            'completed': final_completed,
            'failed': final_failed,
            'pending': expected_count - final_completed - final_failed,
            'completion_time_s': timeout,
            'peak_ocr_queue': self.peak_ocr_queue,
            'peak_fcm_queue': self.peak_fcm_queue,
            'dlq_messages': self.get_queue_depth().get('dlq_queue', 0),
            'notification_count': final_notif,
            'timed_out': True,
        }


# ============================================================
# MQTT 메시지 생성
# ============================================================
GCS_BUCKET = os.getenv('GCS_BUCKET', 'speedcam-bucket-4f918446')
REAL_IMAGES = [f"real-plate-{str(i).zfill(2)}.jpg" for i in range(1, 11)]
_image_counter = 0
_image_lock = threading.Lock()


def verify_gcs_images():
    """GCS 이미지 파일 존재 여부 사전 확인"""
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(f"detections/{REAL_IMAGES[0]}")
        if blob.exists():
            print(f"  [사전확인] GCS 이미지 접근 가능: gs://{GCS_BUCKET}/detections/{REAL_IMAGES[0]}")
            return True
        else:
            print(f"  [경고] GCS 이미지 없음: gs://{GCS_BUCKET}/detections/{REAL_IMAGES[0]}")
            print("  [경고] OCR Worker가 이미지를 찾지 못해 failed 상태가 될 수 있습니다")
            return False
    except Exception as e:
        print(f"  [경고] GCS 접근 확인 실패: {e} (테스트는 계속 진행됩니다)")
        return False


def generate_message(camera_id=None):
    """실제 카메라 감지 메시지 생성 (실제 GCS 이미지 사용)"""
    global _image_counter
    kst = timezone(timedelta(hours=9))
    speed_limit = random.choice([60.0, 80.0, 100.0, 110.0])
    detected_speed = speed_limit + random.uniform(5, 50)

    with _image_lock:
        image_file = REAL_IMAGES[_image_counter % len(REAL_IMAGES)]
        _image_counter += 1

    return json.dumps({
        "camera_id": camera_id or random.choice(CAMERA_IDS),
        "location": random.choice(LOCATIONS),
        "detected_speed": round(detected_speed, 1),
        "speed_limit": speed_limit,
        "detected_at": datetime.now(kst).isoformat(),
        "image_gcs_uri": f"gs://{GCS_BUCKET}/detections/{image_file}",
    })


# ============================================================
# 발행 워커
# ============================================================
class PublishStats:
    """스레드 안전한 발행 통계"""

    def __init__(self):
        self.published = 0
        self.failed = 0
        self.total_latency_ms = 0
        self.start_time = None
        self._lock = threading.Lock()

    def record_success(self, latency_ms):
        with self._lock:
            self.published += 1
            self.total_latency_ms += latency_ms

    def record_failure(self):
        with self._lock:
            self.failed += 1

    @property
    def summary(self):
        with self._lock:
            elapsed = time.time() - self.start_time if self.start_time else 0
            total = self.published + self.failed
            return {
                'published': self.published,
                'failed': self.failed,
                'total': total,
                'elapsed_s': round(elapsed, 1),
                'rate_per_s': round(self.published / elapsed, 2) if elapsed > 0 else 0,
                'avg_latency_ms': round(self.total_latency_ms / self.published, 2) if self.published > 0 else 0,
                'error_rate': round(self.failed / total * 100, 2) if total > 0 else 0,
            }


def publish_worker(worker_id, mqtt_host, mqtt_port, mqtt_user, mqtt_pass,
                   rate_per_sec, duration_sec, stats):
    """단일 카메라 시뮬레이션 워커"""
    camera_id = CAMERA_IDS[worker_id % len(CAMERA_IDS)]

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        protocol=mqtt.MQTTv311,
        client_id=f"loadtest-{worker_id}-{os.getpid()}",
    )
    client.username_pw_set(mqtt_user, mqtt_pass)

    try:
        client.connect(mqtt_host, mqtt_port, keepalive=60)
        client.loop_start()
    except Exception as e:
        print(f"  [Worker-{worker_id}] 연결 실패: {e}")
        stats.record_failure()
        return

    interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 1.0
    end_time = time.time() + duration_sec

    while time.time() < end_time and not shutdown_event.is_set():
        msg = generate_message(camera_id)
        start = time.time()
        result = client.publish(TOPIC, msg, qos=1)

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            latency_ms = (time.time() - start) * 1000
            stats.record_success(latency_ms)
        else:
            stats.record_failure()

        elapsed = time.time() - start
        sleep_time = max(0, interval - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

    client.loop_stop()
    client.disconnect()


# ============================================================
# 메인 테스트 오케스트레이터
# ============================================================
class MQTTLoadTest:
    """MQTT 부하테스트 + 파이프라인 검증 오케스트레이터"""

    def __init__(self, scenario_name, mqtt_host, mqtt_port, mqtt_user, mqtt_pass,
                 api_url=None, rabbitmq_api=None, rabbitmq_user='sa', rabbitmq_pass='',
                 custom_workers=None, custom_rate=None, custom_duration=None):
        if scenario_name == 'custom':
            self.scenario = {
                'description': f'커스텀: {custom_workers} workers, {custom_rate}/s, {custom_duration}s',
                'workers': custom_workers or 5,
                'rate_per_worker': custom_rate or 2,
                'duration': custom_duration or 60,
                'expected_total': int((custom_workers or 5) * (custom_rate or 2) * (custom_duration or 60)),
                'hypothesis': {
                    'publish_success': '-',
                    'completion_rate': '-',
                    'completion_time': '-',
                    'peak_ocr_queue': '-',
                    'dlq_messages': '-',
                    'bottleneck': '(커스텀 시나리오)',
                },
            }
            self.scenario_name = 'custom'
        else:
            self.scenario = SCENARIOS[scenario_name]
            self.scenario_name = scenario_name

        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.mqtt_user = mqtt_user
        self.mqtt_pass = mqtt_pass
        self.stats = PublishStats()

        # 파이프라인 검증 (API 접근 가능 시)
        if api_url and requests:
            self.verifier = PipelineVerifier(
                api_url, rabbitmq_api, rabbitmq_user, rabbitmq_pass
            )
        else:
            self.verifier = None

    def run(self):
        """테스트 실행: 발행 → 검증 → 결과 출력"""
        scenario = self.scenario

        print("\n" + "=" * 70)
        print(f"  MQTT 부하테스트: {scenario['description']}")
        print("=" * 70)
        print(f"  호스트: {self.mqtt_host}:{self.mqtt_port}")
        print(f"  워커 수: {scenario['workers']}")
        rate_total = scenario['workers'] * scenario['rate_per_worker']
        print(f"  발행 속도: {scenario['rate_per_worker']:.4f}/s/worker ({rate_total:.2f}/s 총)")
        print(f"  지속 시간: {scenario['duration']}초")
        print(f"  예상 총 메시지: {scenario['expected_total']}건")
        print(f"  파이프라인 검증: {'활성' if self.verifier else '비활성'}")
        print("=" * 70)

        # Phase 0: GCS 이미지 사전 확인
        verify_gcs_images()

        # Phase 1: 기준선 기록
        baseline = None
        if self.verifier:
            baseline = self.verifier.get_detection_stats()
            if baseline:
                print(f"\n  [기준선] 현재 통계 - "
                      f"total: {baseline.get('total_detections', 0)}, "
                      f"completed: {baseline.get('completed_count', 0)}, "
                      f"failed: {baseline.get('failed_count', 0)}, "
                      f"pending: {baseline.get('pending_count', 0)}")
            else:
                print("\n  [기준선] 통계 조회 실패 - 파이프라인 검증 건너뜀")

        # Phase 2: MQTT 발행
        print(f"\n  [발행 시작] {scenario['workers']}개 워커 실행 중...")
        self.stats.start_time = time.time()
        threads = []

        for i in range(scenario['workers']):
            t = threading.Thread(
                target=publish_worker,
                args=(i, self.mqtt_host, self.mqtt_port,
                      self.mqtt_user, self.mqtt_pass,
                      scenario['rate_per_worker'], scenario['duration'],
                      self.stats),
                daemon=True,
            )
            t.start()
            threads.append(t)

        # 발행 중 주기적 상태 출력
        monitor_end = time.time() + scenario['duration']
        while time.time() < monitor_end and not shutdown_event.is_set():
            time.sleep(5)
            s = self.stats.summary
            print(f"  [{s['elapsed_s']}s] 발행: {s['published']} | "
                  f"실패: {s['failed']} | 속도: {s['rate_per_s']} msg/s")

        for t in threads:
            t.join(timeout=10)

        publish_summary = self.stats.summary
        print(f"\n  [발행 완료] {publish_summary['published']}건 발행, "
              f"{publish_summary['failed']}건 실패")

        # Phase 3: 파이프라인 검증
        pipeline_result = None
        if self.verifier and baseline:
            pipeline_result = self.verifier.wait_for_completion(
                expected_count=scenario['expected_total'],
                baseline_stats=baseline,
                timeout=300,
                poll_interval=5,
            )

        # Phase 4: 결과 출력
        self._print_results(publish_summary, pipeline_result)

    def _print_results(self, publish_summary, pipeline_result):
        """구조화된 결과 출력 + 가설 비교 템플릿"""
        hypothesis = self.scenario.get('hypothesis', {})

        print("\n")
        print("=" * 70)
        print(f"  결과: {self.scenario['description']}")
        print("=" * 70)

        # 발행 결과
        print("\n  [발행 결과]")
        print(f"    발행 성공: {publish_summary['published']}건")
        print(f"    발행 실패: {publish_summary['failed']}건")
        print(f"    발행 속도: {publish_summary['rate_per_s']} msg/s")
        print(f"    평균 지연: {publish_summary['avg_latency_ms']}ms")
        print(f"    에러율: {publish_summary['error_rate']}%")

        # 파이프라인 결과
        if pipeline_result:
            total_done = pipeline_result['completed'] + pipeline_result['failed']
            expected = self.scenario['expected_total']
            completion_pct = round(total_done / expected * 100, 1) if expected > 0 else 0

            print("\n  [파이프라인 완료]")
            print(f"    완료: {pipeline_result['completed']}/{expected} ({completion_pct}%)")
            print(f"    실패: {pipeline_result['failed']}건")
            print(f"    대기 중: {pipeline_result['pending']}건")
            print(f"    E2E 소요: {pipeline_result['completion_time_s']}초"
                  + (" (타임아웃)" if pipeline_result.get('timed_out') else ""))
            print(f"    OCR 큐 피크: {pipeline_result['peak_ocr_queue']}")
            print(f"    FCM 큐 피크: {pipeline_result['peak_fcm_queue']}")
            print(f"    DLQ 메시지: {pipeline_result.get('dlq_messages', '-')}")
            print(f"    알림 생성: {pipeline_result.get('notification_count', '-')}")
        else:
            print("\n  [파이프라인 검증] 비활성 (API URL 미설정 또는 requests 패키지 없음)")

        # 가설 비교 템플릿
        actual_success = f"{100 - publish_summary['error_rate']:.1f}%"
        actual_completion = '-'
        actual_e2e = '-'
        actual_ocr_peak = '-'
        actual_dlq = '-'

        if pipeline_result:
            expected = self.scenario['expected_total']
            total_done = pipeline_result['completed'] + pipeline_result['failed']
            actual_completion = f"{round(total_done / expected * 100, 1) if expected > 0 else 0}%"
            actual_e2e = f"{pipeline_result['completion_time_s']}초"
            actual_ocr_peak = str(pipeline_result['peak_ocr_queue'])
            actual_dlq = str(pipeline_result.get('dlq_messages', '-'))

        print("\n  [가설 비교]")
        print(f"    {'지표':<25} {'가설':<20} {'실제':<15} {'판정'}")
        print(f"    {'-'*75}")
        print(f"    {'발행 성공률':<23} {hypothesis.get('publish_success', '-'):<20} {actual_success:<15}")
        print(f"    {'파이프라인 완료율':<20} {hypothesis.get('completion_rate', '-'):<20} {actual_completion:<15}")
        print(f"    {'E2E 완료 시간':<21} {hypothesis.get('completion_time', '-'):<20} {actual_e2e:<15}")
        print(f"    {'OCR 큐 피크':<22} {hypothesis.get('peak_ocr_queue', '-'):<20} {actual_ocr_peak:<15}")
        print(f"    {'DLQ 메시지':<23} {hypothesis.get('dlq_messages', '-'):<20} {actual_dlq:<15}")
        print(f"    {'알림 생성 수':<22} {'≈ 완료 수':<20} {str(pipeline_result.get('notification_count', '-')) if pipeline_result else '-':<15}")
        print(f"    {'예상 병목':<23} {hypothesis.get('bottleneck', '-')}")

        print("\n  [병목 분석]")
        print("    Grafana/Prometheus 메트릭을 확인하여 아래 항목을 채우세요:")
        print("    - Gunicorn worker 포화 여부:")
        print("    - MySQL 연결 수:")
        print("    - OCR Worker 처리 속도:")
        print("    - MQTT Subscriber 처리 지연:")

        print("\n" + "=" * 70)


# ============================================================
# 시그널 핸들러 (graceful shutdown)
# ============================================================
def signal_handler(signum, frame):
    print(f"\n  [종료 신호 수신] 워커 중단 중...")
    shutdown_event.set()


# ============================================================
# CLI 인터페이스
# ============================================================
def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser(
        description="MQTT 파이프라인 부하테스트 - IoT 카메라 시뮬레이션",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
시나리오 설명:
  normal     정상 운영: 20대 카메라, 1건/분 (0.33 msg/s)
  rush_hour  러시아워: 20대 카메라, 5건/분 (1.67 msg/s)
  burst      버스트 스톰: 20대 카메라, 1건/초 (20 msg/s)

사용 예시:
  # 정상 운영 시나리오 (파이프라인 검증 포함)
  python3 mqtt-load-test.py --scenario normal \\
    --api-url http://speedcam-app:8000 \\
    --rabbitmq-api http://speedcam-mq:15672 \\
    --rabbitmq-user sa --rabbitmq-pass $RABBITMQ_PASS

  # 커스텀 설정 (하위 호환)
  python3 mqtt-load-test.py --workers 10 --rate 5 --duration 30
        """
    )

    # 시나리오 선택
    parser.add_argument(
        '--scenario', choices=['normal', 'rush_hour', 'burst'],
        default=None, help='사전 정의 시나리오 (normal/rush_hour/burst)'
    )

    # MQTT 설정
    parser.add_argument(
        '--mqtt-host', default=os.getenv('MQTT_HOST', 'rabbitmq'),
        help='MQTT 브로커 호스트 (기본: MQTT_HOST 환경변수 또는 rabbitmq)'
    )
    parser.add_argument(
        '--mqtt-port', type=int, default=int(os.getenv('MQTT_PORT', '1883')),
        help='MQTT 브로커 포트 (기본: 1883)'
    )
    parser.add_argument(
        '--mqtt-user', default=os.getenv('MQTT_USER', 'sa'),
        help='MQTT 사용자 (기본: sa)'
    )
    parser.add_argument(
        '--mqtt-pass', default=os.getenv('MQTT_PASS', ''),
        help='MQTT 비밀번호 (기본: MQTT_PASS 환경변수)'
    )

    # 파이프라인 검증
    parser.add_argument(
        '--api-url', default=None,
        help='SpeedCam API URL (예: http://speedcam-app:8000). 설정 시 파이프라인 검증 활성화'
    )
    parser.add_argument(
        '--rabbitmq-api', default=None,
        help='RabbitMQ Management API URL (예: http://speedcam-mq:15672)'
    )
    parser.add_argument(
        '--rabbitmq-user', default=os.getenv('RABBITMQ_USER', 'sa'),
        help='RabbitMQ Management API 사용자 (기본: sa)'
    )
    parser.add_argument(
        '--rabbitmq-pass', default=os.getenv('RABBITMQ_PASS', ''),
        help='RabbitMQ Management API 비밀번호 (기본: RABBITMQ_PASS 환경변수)'
    )

    # 커스텀 설정 (하위 호환)
    parser.add_argument(
        '--workers', type=int, default=None,
        help='워커 수 (--scenario 미지정 시 사용, 기본: 5)'
    )
    parser.add_argument(
        '--rate', type=float, default=None,
        help='워커당 초당 발행 수 (--scenario 미지정 시 사용, 기본: 2)'
    )
    parser.add_argument(
        '--duration', type=int, default=None,
        help='테스트 시간(초) (--scenario 미지정 시 사용, 기본: 60)'
    )

    args = parser.parse_args()

    # 시나리오 결정: --scenario 지정 시 사용, 아니면 커스텀
    if args.scenario:
        scenario_name = args.scenario
    elif args.workers is not None or args.rate is not None or args.duration is not None:
        scenario_name = 'custom'
    else:
        scenario_name = 'normal'
        print("  [INFO] --scenario 미지정, 기본값 'normal' 사용")

    test = MQTTLoadTest(
        scenario_name=scenario_name,
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        mqtt_user=args.mqtt_user,
        mqtt_pass=args.mqtt_pass,
        api_url=args.api_url,
        rabbitmq_api=args.rabbitmq_api,
        rabbitmq_user=args.rabbitmq_user,
        rabbitmq_pass=args.rabbitmq_pass,
        custom_workers=args.workers or 5,
        custom_rate=args.rate or 2,
        custom_duration=args.duration or 60,
    )

    test.run()


if __name__ == "__main__":
    main()
