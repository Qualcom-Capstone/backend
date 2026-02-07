#!/usr/bin/env python3
"""
MQTT Load Test - IoT Device Simulation

Simulates Raspberry Pi cameras sending detection messages via MQTT.
Full pipeline: MQTT → Detection (pending) → OCR Worker → Alert Worker
"""

import argparse
import json
import os
import random
import threading
import time
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt

# Config from environment
MQTT_HOST = os.getenv("MQTT_HOST", "rabbitmq")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "sa")
MQTT_PASS = os.getenv("MQTT_PASS", "1234")
TOPIC = "detections/new"

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

# Stats
stats = {
    "published": 0,
    "failed": 0,
    "total_latency_ms": 0,
    "start_time": None,
}
stats_lock = threading.Lock()


def generate_message():
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
                f"gs://speedcam-bucket/detections/"
                f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}.jpg"
            ),
        }
    )


def publish_worker(worker_id, rate_per_sec, duration_sec):
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
    print(f"  Rate: {rate:.1f} msg/s | Avg Latency: {avg_latency:.2f}ms")
    print(f"  Error Rate: {(failed/total*100) if total > 0 else 0:.2f}%")
    print(f"{'='*60}")


def run_load_test(workers, rate_per_worker, duration):
    """Run the load test with multiple workers."""
    print("\n MQTT Load Test Starting")
    print(f"  Host: {MQTT_HOST}:{MQTT_PORT}")
    print(f"  Workers: {workers}")
    print(
        f"  Rate: {rate_per_worker}/s per worker ({workers * rate_per_worker}/s total)"
    )
    print(f"  Duration: {duration}s")
    print(f"  Topic: {TOPIC}")
    print()

    stats["start_time"] = time.time()
    threads = []

    for i in range(workers):
        t = threading.Thread(
            target=publish_worker,
            args=(i, rate_per_worker, duration),
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

    print("\n FINAL RESULTS")
    print_stats()


def main():
    parser = argparse.ArgumentParser(description="MQTT Load Test")
    parser.add_argument(
        "--workers", type=int, default=5, help="Number of concurrent workers"
    )
    parser.add_argument(
        "--rate", type=int, default=2, help="Messages per second per worker"
    )
    parser.add_argument(
        "--duration", type=int, default=60, help="Test duration in seconds"
    )
    args = parser.parse_args()

    run_load_test(args.workers, args.rate, args.duration)


if __name__ == "__main__":
    main()
