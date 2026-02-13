#!/usr/bin/env python3
"""
MQTT Full Pipeline Load Test
Full pipeline: MQTT → Main → AMQP → OCR (EasyOCR) → AMQP Event → Alert

Usage:
  python mqtt-load-test.py smoke
  python mqtt-load-test.py baseline
  python mqtt-load-test.py saturation
  python mqtt-load-test.py spike
  python mqtt-load-test.py sustained
"""

import argparse
import json
import os
import random
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import paho.mqtt.client as mqtt

# Config from environment
MQTT_HOST = os.getenv("MQTT_HOST", "10.178.0.7")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "sa")
MQTT_PASS = os.getenv("MQTT_PASS", "1234")
TOPIC = "detections/new"

# Database config
DB_HOST = os.getenv("DB_HOST", "10.178.0.2")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "sa")
DB_PASS = os.getenv("DB_PASS", "hG57vv9aJHPGm0X82xlQ")
DB_NAME = os.getenv("DB_NAME_DETECTIONS", "speedcam_detections")

# GCS 설정
GCS_BUCKET = os.getenv("GCS_BUCKET", "speedcam-bucket-4f918446")
GCS_IMAGES = (
    [f"real-plate-{str(i).zfill(2)}.jpg" for i in range(1, 11)]
    + [f"plate-{str(i).zfill(2)}.jpg" for i in range(1, 11)]
    + [f"test-plate-{i}.jpg" for i in range(1, 6)]
)

# Locations for realistic simulation
LOCATIONS = [
    "서울시 강남구 테헤란로",
    "서울시 서초구 반포대로",
    "서울시 송파구 올림픽로",
    "경기도 성남시 분당구 판교역로",
    "인천시 연수구 송도대로",
    "서울시 마포구 월드컵북로",
    "서울시 영등포구 여의대방로",
    "부산시 해운대구 해운대로",
]

CAMERA_IDS = [f"CAM-{str(i).zfill(3)}" for i in range(1, 21)]

# Scenario definitions
SCENARIOS = {
    "smoke": {
        "workers": 1,
        "rate": 0,  # Manual single message
        "duration": 0,
        "expected_messages": 1,
        "expected_throughput": 0.2,
        "expected_queue_depth": 0,
        "expected_error_rate": 0,
        "description": "Verify pipeline works end-to-end",
    },
    "baseline": {
        "workers": 1,
        "rate": 0.2,
        "duration": 60,
        "expected_messages": 12,
        "expected_throughput": 0.2,
        "expected_queue_depth": 0,
        "expected_error_rate": 1,
        "description": "Match OCR capacity, measure steady-state latency",
    },
    "saturation": {
        "workers": 3,
        "rate": 1,
        "duration": 60,
        "expected_messages": 180,
        "expected_throughput": 0.2,
        "expected_queue_depth": 168,  # ~180 - 12 processed
        "expected_error_rate": 1,
        "description": "Exceed OCR capacity to test queuing behavior",
    },
    "spike": {
        "workers": 5,
        "rate": 2,
        "duration": 10,
        "expected_messages": 100,
        "expected_throughput": 0.2,
        "expected_queue_depth": 98,  # ~100 - 2 processed
        "expected_error_rate": 1,
        "description": "Sudden burst, measure recovery",
    },
    "sustained": {
        "workers": 2,
        "rate": 0.5,
        "duration": 300,
        "expected_messages": 300,
        "expected_throughput": 0.2,
        "expected_queue_depth": 240,  # ~300 - 60 processed
        "expected_error_rate": 1,
        "description": "Long-running stability test",
    },
}

# Stats
stats = {
    "published": 0,
    "failed": 0,
    "total_latency_ms": 0,
    "start_time": None,
}
stats_lock = threading.Lock()


def generate_message() -> str:
    """Generate a realistic detection message."""
    kst = timezone(timedelta(hours=9))
    speed_limit = random.choice([60.0, 80.0, 100.0, 110.0])
    detected_speed = speed_limit + random.uniform(5, 50)

    return json.dumps(
        {
            "camera_id": random.choice(CAMERA_IDS),
            "location": random.choice(LOCATIONS),
            "detected_speed": round(detected_speed, 1),
            "speed_limit": speed_limit,
            "detected_at": datetime.now(kst).isoformat(),
            "image_gcs_uri": (
                f"gs://{GCS_BUCKET}/detections/{random.choice(GCS_IMAGES)}"
            ),
        }
    )


def publish_single_message() -> bool:
    """Publish a single message for smoke test."""
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        protocol=mqtt.MQTTv311,
        client_id=f"loadtest-smoke-{os.getpid()}",
    )
    client.username_pw_set(MQTT_USER, MQTT_PASS)

    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()
        time.sleep(0.5)  # Allow connection to establish

        msg = generate_message()
        start = time.time()
        result = client.publish(TOPIC, msg, qos=1)
        result.wait_for_publish(timeout=5)

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            latency_ms = (time.time() - start) * 1000
            print(f"✓ Message published successfully (latency: {latency_ms:.2f}ms)")
            print(f"  Payload: {msg[:100]}...")
            with stats_lock:
                stats["published"] = 1
                stats["total_latency_ms"] = latency_ms
            return True
        else:
            print(f"✗ Publish failed with code {result.rc}")
            with stats_lock:
                stats["failed"] = 1
            return False
    except Exception as e:
        print(f"✗ Exception during publish: {e}")
        with stats_lock:
            stats["failed"] = 1
        return False
    finally:
        client.loop_stop()
        client.disconnect()


def publish_worker(worker_id: int, rate_per_sec: float, duration_sec: int):
    """Single worker thread that publishes MQTT messages."""
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        protocol=mqtt.MQTTv311,
        client_id=f"loadtest-{worker_id}-{os.getpid()}",
    )
    client.username_pw_set(MQTT_USER, MQTT_PASS)

    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()
    except Exception as e:
        print(f"[Worker-{worker_id}] Connection failed: {e}")
        with stats_lock:
            stats["failed"] += 1
        return

    interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 1.0
    end_time = time.time() + duration_sec

    while time.time() < end_time:
        msg = generate_message()
        start = time.time()
        result = client.publish(TOPIC, msg, qos=1)

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            latency_ms = (time.time() - start) * 1000
            with stats_lock:
                stats["published"] += 1
                stats["total_latency_ms"] += latency_ms
        else:
            with stats_lock:
                stats["failed"] += 1

        elapsed = time.time() - start
        sleep_time = max(0, interval - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

    client.loop_stop()
    client.disconnect()


def print_stats():
    """Print periodic stats."""
    elapsed = time.time() - stats["start_time"]
    published = stats["published"]
    failed = stats["failed"]
    total = published + failed
    rate = published / elapsed if elapsed > 0 else 0
    avg_latency = stats["total_latency_ms"] / published if published > 0 else 0

    print(f"\n{'='*60}")
    print(f"  Elapsed: {elapsed:.1f}s | Published: {published} | Failed: {failed}")
    print(f"  Rate: {rate:.2f} msg/s | Avg Latency: {avg_latency:.2f}ms")
    print(f"  Error Rate: {(failed/total*100) if total > 0 else 0:.2f}%")
    print(f"{'='*60}")


def get_db_connection():
    """Try to import and connect to MySQL database."""
    # Try pymysql first
    try:
        import pymysql
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        return conn, 'pymysql'
    except ImportError:
        pass
    except Exception as e:
        print(f"⚠ pymysql connection failed: {e}")

    # Try mysql.connector
    try:
        import mysql.connector
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            charset='utf8mb4'
        )
        return conn, 'mysql.connector'
    except ImportError:
        pass
    except Exception as e:
        print(f"⚠ mysql.connector connection failed: {e}")

    return None, None


def verify_pipeline(expected_count: int, max_wait_sec: int = 30) -> Optional[Dict]:
    """Verify the pipeline by querying MySQL database."""
    conn, driver = get_db_connection()
    if not conn:
        print("\n⚠ WARNING: No MySQL driver available (pymysql or mysql-connector-python)")
        print("   Pipeline verification skipped. Install pymysql to enable:")
        print("   pip install pymysql")
        return None

    print(f"\n{'='*60}")
    print("=== PIPELINE VERIFICATION ===")
    print(f"  Database: {DB_HOST}:{DB_PORT}/{DB_NAME} (driver: {driver})")
    print(f"{'='*60}")

    try:
        cursor = conn.cursor()

        # Initial check
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM detections
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 10 MINUTE)
        """)

        if driver == 'pymysql':
            result = cursor.fetchone()
        else:  # mysql.connector
            result = cursor.fetchone()
            # Convert tuple to dict for mysql.connector
            columns = [desc[0] for desc in cursor.description]
            result = dict(zip(columns, result))

        initial_total = result['total'] or 0
        print(f"\nInitial state (last 10 minutes):")
        print(f"  Total detections: {initial_total}")
        print(f"  - completed: {result['completed'] or 0}")
        print(f"  - processing: {result['processing'] or 0}")
        print(f"  - pending: {result['pending'] or 0}")
        print(f"  - failed: {result['failed'] or 0}")

        # Wait for pipeline to process
        if max_wait_sec > 0:
            print(f"\nWaiting up to {max_wait_sec}s for pipeline to drain...")
            wait_start = time.time()
            while time.time() - wait_start < max_wait_sec:
                cursor.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                        SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing,
                        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                    FROM detections
                    WHERE created_at >= DATE_SUB(NOW(), INTERVAL 10 MINUTE)
                """)

                if driver == 'pymysql':
                    result = cursor.fetchone()
                else:
                    result = cursor.fetchone()
                    columns = [desc[0] for desc in cursor.description]
                    result = dict(zip(columns, result))

                processing = result['processing'] or 0
                pending = result['pending'] or 0

                if processing == 0 and pending == 0:
                    print(f"✓ Pipeline drained after {time.time() - wait_start:.1f}s")
                    break

                print(f"  [{time.time() - wait_start:.1f}s] processing: {processing}, pending: {pending}")
                time.sleep(2)

        # Final status
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM detections
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 10 MINUTE)
        """)

        if driver == 'pymysql':
            final_result = cursor.fetchone()
        else:
            final_result = cursor.fetchone()
            columns = [desc[0] for desc in cursor.description]
            final_result = dict(zip(columns, final_result))

        print(f"\nFinal state:")
        print(f"  Total detections created: {final_result['total']}")
        print(f"  - completed: {final_result['completed'] or 0}")
        print(f"  - processing: {final_result['processing'] or 0}")
        print(f"  - pending: {final_result['pending'] or 0}")
        print(f"  - failed: {final_result['failed'] or 0}")

        total = final_result['total'] or 0
        completed = final_result['completed'] or 0
        completion_rate = (completed / total * 100) if total > 0 else 0
        print(f"  Pipeline completion rate: {completed}/{total} = {completion_rate:.1f}%")

        cursor.close()
        return final_result
    except Exception as e:
        print(f"✗ Pipeline verification error: {e}")
        return None
    finally:
        conn.close()


def print_hypothesis(scenario_name: str, config: Dict):
    """Print hypothesis for the scenario."""
    print(f"\n{'='*60}")
    print("=== HYPOTHESIS ===")
    print(f"  Scenario: {scenario_name.upper()} - {config['description']}")
    print(f"  Expected published: {config['expected_messages']} messages")
    print(f"  Expected OCR throughput: ~{config['expected_throughput']} msg/s (OCR_CONCURRENCY=1, ~5s/image)")
    if config['duration'] > 0:
        expected_processed = int(config['expected_throughput'] * config['duration'])
        print(f"  Expected processed in {config['duration']}s: ~{expected_processed} messages")
    print(f"  Expected queue depth at end: ~{config['expected_queue_depth']} messages")
    print(f"  Expected error rate: <{config['expected_error_rate']}%")
    print(f"{'='*60}\n")


def print_comparison(scenario_name: str, config: Dict, db_result: Optional[Dict]):
    """Print comparison between hypothesis and actual results."""
    print(f"\n{'='*60}")
    print("=== COMPARISON ===")

    # Published vs Expected
    published = stats["published"]
    expected_pub = config["expected_messages"]
    pub_match = abs(published - expected_pub) <= max(1, expected_pub * 0.1)  # 10% tolerance
    print(f"  Published: {published} vs Expected: {expected_pub} {'✓ PASS' if pub_match else '✗ FAIL'}")

    # Error rate
    failed = stats["failed"]
    total = published + failed
    actual_error_rate = (failed / total * 100) if total > 0 else 0
    expected_error_rate = config["expected_error_rate"]
    error_match = actual_error_rate <= expected_error_rate
    print(f"  Error rate: {actual_error_rate:.2f}% vs Expected: <{expected_error_rate}% {'✓ PASS' if error_match else '✗ FAIL'}")

    # Queue depth (from DB if available)
    if db_result:
        processing = db_result['processing'] or 0
        pending = db_result['pending'] or 0
        actual_queue = processing + pending
        expected_queue = config['expected_queue_depth']
        print(f"  Queue depth: {actual_queue} vs Expected: ~{expected_queue} (INFO)")

        # Pipeline completion
        completed = db_result['completed'] or 0
        db_total = db_result['total'] or 0
        if db_total > 0:
            completion_rate = completed / db_total * 100
            print(f"  Pipeline completion: {completion_rate:.1f}% ({completed}/{db_total})")

    print(f"{'='*60}\n")


def run_scenario(scenario_name: str):
    """Run a specific test scenario."""
    if scenario_name not in SCENARIOS:
        print(f"✗ Unknown scenario: {scenario_name}")
        print(f"  Available scenarios: {', '.join(SCENARIOS.keys())}")
        sys.exit(1)

    config = SCENARIOS[scenario_name]

    # Print hypothesis
    print_hypothesis(scenario_name, config)

    # Handle smoke test separately
    if scenario_name == "smoke":
        print("=== EXECUTION (SMOKE TEST) ===")
        print("Publishing single message...\n")
        stats["start_time"] = time.time()
        success = publish_single_message()

        if success:
            print("\n=== RESULTS ===")
            print(f"  Published: 1 | Failed: 0")
            print(f"  Avg Latency: {stats['total_latency_ms']:.2f}ms")

            # Wait a bit for pipeline
            print("\nWaiting 10s for pipeline to process...")
            time.sleep(10)

            # Verify pipeline
            db_result = verify_pipeline(expected_count=1, max_wait_sec=20)

            # Print comparison
            print_comparison(scenario_name, config, db_result)
        else:
            print("\n✗ Smoke test failed - message not published")
            sys.exit(1)

        return

    # Regular load test
    workers = config["workers"]
    rate = config["rate"]
    duration = config["duration"]

    print("=== EXECUTION ===")
    print(f"  Host: {MQTT_HOST}:{MQTT_PORT}")
    print(f"  Workers: {workers}")
    print(f"  Rate: {rate}/s per worker ({workers * rate}/s total)")
    print(f"  Duration: {duration}s")
    print(f"  Topic: {TOPIC}\n")

    stats["start_time"] = time.time()
    threads = []

    for i in range(workers):
        t = threading.Thread(
            target=publish_worker,
            args=(i, rate, duration),
        )
        t.start()
        threads.append(t)

    # Print stats periodically
    monitor_end = time.time() + duration
    while time.time() < monitor_end:
        time.sleep(5)
        print_stats()

    for t in threads:
        t.join(timeout=10)

    # Final results
    print("\n=== RESULTS ===")
    elapsed = time.time() - stats["start_time"]
    published = stats["published"]
    failed = stats["failed"]
    total = published + failed
    rate_actual = published / elapsed if elapsed > 0 else 0
    avg_latency = stats["total_latency_ms"] / published if published > 0 else 0

    print(f"  Published: {published} | Failed: {failed}")
    print(f"  Rate: {rate_actual:.2f} msg/s | Avg Latency: {avg_latency:.2f}ms")
    print(f"  Error Rate: {(failed/total*100) if total > 0 else 0:.2f}%")

    # Verify pipeline
    wait_time = min(30, duration // 2)  # Wait up to 30s or half test duration
    db_result = verify_pipeline(expected_count=published, max_wait_sec=wait_time)

    # Print comparison
    print_comparison(scenario_name, config, db_result)


def main():
    parser = argparse.ArgumentParser(
        description="MQTT Full Pipeline Load Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available scenarios:
  smoke       - Verify pipeline works end-to-end (1 message)
  baseline    - Match OCR capacity (1 worker, 0.2 msg/s, 60s)
  saturation  - Exceed OCR capacity (3 workers, 1 msg/s, 60s)
  spike       - Sudden burst (5 workers, 2 msg/s, 10s)
  sustained   - Long-running stability (2 workers, 0.5 msg/s, 300s)

Examples:
  python mqtt-load-test.py smoke
  python mqtt-load-test.py baseline
  python mqtt-load-test.py saturation
        """
    )
    parser.add_argument(
        "scenario",
        choices=list(SCENARIOS.keys()),
        help="Test scenario to run"
    )

    args = parser.parse_args()

    # Verify MQTT credentials
    if not MQTT_PASS:
        print("✗ Error: MQTT_PASS environment variable not set")
        sys.exit(1)

    run_scenario(args.scenario)


if __name__ == "__main__":
    main()
